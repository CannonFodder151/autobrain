#pragma once

#include <NimBLEDevice.h>
#include <esp_system.h>

#include "config.h"
#include "obd_pids.h"
#include "prov_validate.h"
#include "wifi_cfg.h"

// BLE service exposing trip data for the AutoBrain app to pull later, plus a
// provisioning characteristic the app writes once with the WiFi upload config
// (AUT-918). PoC scope: device advertises + exposes trip list over GATT. Full
// file transfer / pairing is the app-side sync phase.
// ponytail: one characteristic per trip would be cleaner, but for the PoC a
// single LIST characteristic + index file is enough; add file-transfer when
// the app sync client exists.
static const char* BLE_SERVICE_UUID  = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E";
static const char* BLE_CHAR_LIST_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E";
static const char* BLE_CHAR_PROV_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E";
// F2 (AUT-969): one-shot provisioning token. The app must READ this
// characteristic (a fresh random token minted when the provisioning window
// opens) and echo the value back inside the config payload as "prov_token".
// The firmware validates the echo and consumes the token on the first valid
// write, so a BLE peer that connects first can't push an attacker-chosen
// config, and a captured/replayed write is rejected.
static const char* BLE_CHAR_PROV_TOKEN_UUID = "6E400004-B5A3-F393-E0A9-E50E24DCCA9E";

// Minimal deterministic extractor for `"key":"value"` pairs in the small
// provisioning JSON object. No JSON lib on the edge — we only ever accept this
// fixed shape. The app cards the exact payload format.
namespace autobrain {
inline bool json_get_str(const char* json, const char* key, char* out, size_t n) {
    out[0] = '\0';
    size_t klen = strlen(key);
    const char* k = strstr(json, key);
    if (!k) return false;
    const char* colon = k + klen;
    while (*colon && *colon != ':' && *colon != '\n') colon++;
    if (*colon != ':') return false;
    const char* q = colon + 1;
    while (*q == ' ' || *q == '\t') q++;
    if (*q != '"') return false;
    q++;
    size_t used = 0;
    while (*q && *q != '"' && used + 1 < n) out[used++] = *q++;
    out[used] = '\0';
    return *q == '"';
}
}  // namespace autobrain

class BleSync {
public:
    void begin(const char* name) {
        _name = name;
        NimBLEDevice::init(name);
        _ble_on = true;
        // Security Fw1: require pairing + bonding (MITM) so the provisioning
        // characteristic is only writable by a paired app. Combined with the
        // first-write-only gate below, an on-range attacker can neither
        // overwrite the WiFi creds nor re-point api_url without pairing.
        // F2 (AUT-969): also require Secure Connections (LESC) — legacy Just
        // Works offers no MITM protection; LESC encrypts the link (beats plain
        // sniffing of the provisioning payload). Note: the dongle is headless
        // (NoInputNoOutput), so pairing degrades to Just Works — encrypted but
        // NOT authenticated (no key confirmation / MITM detection). Authenticated
        // pairing (numeric comparison / OOB) is infeasible on this hardware;
        // accepted residual per AUT-962 F2.
        NimBLEDevice::setSecurityAuth(true, true, true);  // bonding, MITM, SC
        NimBLEServer* server = NimBLEDevice::createServer();
        NimBLEService* svc = server->createService(BLE_SERVICE_UUID);
        _list = svc->createCharacteristic(BLE_CHAR_LIST_UUID,
                                          NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);
        // F2: one-shot provisioning token, readable (post-pairing) before the
        // app writes the config. Minted fresh on every provisioning-window
        // open; consumed on the first valid write.
        _provToken = svc->createCharacteristic(BLE_CHAR_PROV_TOKEN_UUID,
                                               NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::READ_ENC);
        mintProvisionToken();
        _provToken->setValue((uint8_t*)_prov_token, strlen(_prov_token));
        _prov_open_ms = millis();
        // Provisioning (first-time setup): the app writes the WiFi + account
        // config here once; the board persists it to NVS and replies "ok".
        // First-write-only: once enabled, further writes are rejected so a
        // nearby attacker cannot re-provision the device (Fw1).
        _prov = svc->createCharacteristic(BLE_CHAR_PROV_UUID,
                                          NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_ENC);
        _prov->setCallbacks(new ProvisionCallbacks(_prov, _prov_token, _provToken,
                                                   &_prov_open_ms));
        svc->start();
        advertise();
    }

    void publishTrips(const String& index) {
        _list->setValue((uint8_t*)index.c_str(), index.length());
        _list->notify();
    }

    void advertise() {
        if (!_ble_on) return;
        NimBLEDevice::getAdvertising()->addServiceUUID(BLE_SERVICE_UUID);
        NimBLEDevice::getAdvertising()->setName(_name);
        NimBLEDevice::getAdvertising()->start();
    }

    void stopAdvertising() {
        if (!_ble_on) return;
        if (NimBLEDevice::getAdvertising()->isAdvertising())
            NimBLEDevice::getAdvertising()->stop();
    }

    // WiFi upload needs the radio; suspend advertising so STA connects cleanly.
    void wifi_window(bool on) {
        if (on) stopAdvertising(); else advertise();
    }

private:
    NimBLECharacteristic* _list = nullptr;
    NimBLECharacteristic* _prov = nullptr;
    NimBLECharacteristic* _provToken = nullptr;
    const char* _name = "";
    bool _ble_on = false;
    // F2 (AUT-969): one-shot provisioning token + window deadline, so onWrite
    // can enforce the token echo and the PROVISION_WINDOW_MS even after the
    // setup() window loop has moved on.
    char _prov_token[PROV_TOKEN_HEX_LEN + 1] = "";
    uint32_t _prov_open_ms = 0;

    void mintProvisionToken() {
        uint32_t hi = esp_random(), lo = esp_random();
        snprintf(_prov_token, sizeof _prov_token, "%08lx%08lx",
                 (unsigned long)hi, (unsigned long)lo);
    }

    class ProvisionCallbacks : public NimBLECharacteristicCallbacks {
    public:
        explicit ProvisionCallbacks(NimBLECharacteristic* c, char* token,
                                    NimBLECharacteristic* prov_token_char,
                                    uint32_t* open_ms)
            : _c(c), _token(token), _provTokenChar(prov_token_char), _open_ms(open_ms) {}
        void onWrite(NimBLECharacteristic* c, NimBLEConnInfo&) override {
            std::string v = c->getValue();
            const char* json = v.c_str();
            char ssid[33], pass[64], url[128], dev[40], key[80],
                 tok[PROV_TOKEN_HEX_LEN + 1];
            autobrain::json_get_str(json, "ssid", ssid, sizeof ssid);
            autobrain::json_get_str(json, "pass", pass, sizeof pass);
            autobrain::json_get_str(json, "api_url", url, sizeof url);
            autobrain::json_get_str(json, "device_id", dev, sizeof dev);
            autobrain::json_get_str(json, "api_key", key, sizeof key);
            autobrain::json_get_str(json, "prov_token", tok, sizeof tok);
            if (!ssid[0] || !dev[0] || !key[0]) {
                _c->setValue((uint8_t*)"err:need ssid,device_id,api_key", 31);
                return;
            }
            // F2 (AUT-969): the write must echo the one-shot token the app
            // read from BLE_CHAR_PROV_TOKEN_UUID, and it must land inside the
            // PROVISION_WINDOW_MS. Pure helpers live in prov_validate.h so the
            // host self-check can assert them.
            if (!autobrain::provision_token_ok(tok, _token) ||
                !autobrain::provision_window_open(millis() - *_open_ms,
                                                  PROVISION_WINDOW_MS)) {
                _c->setValue((uint8_t*)"err:token missing or expired", 30);
                return;
            }
            // Fw1: first-write-only. A device that already has WiFi upload
            // enabled rejects any later provisioning write — only a factory
            // reset (wifi_cfg_clear) re-arms it.
            autobrain::WifiCfg existing;
            Preferences prefs;
            autobrain::wifi_cfg_load(existing, prefs);
            if (!autobrain::provision_write_allowed(existing.enabled)) {
                _c->setValue((uint8_t*)"err:already configured", 22);
                return;
            }
            // Fw4: api_url must be https-only and device_id UUID-shaped so a
            // bad config fails at provision time, not at first upload.
            const char* api_url = url[0] ? url : DEFAULT_API_URL;
            if (!autobrain::https_url_ok(api_url)) {
                _c->setValue((uint8_t*)"err:api_url must be https", 26);
                return;
            }
            if (!autobrain::uuid_shape_ok(dev)) {
                _c->setValue((uint8_t*)"err:device_id must be a UUID", 30);
                return;
            }
            autobrain::WifiCfg cfg;
            snprintf(cfg.ssid, sizeof cfg.ssid, "%s", ssid);
            snprintf(cfg.pass, sizeof cfg.pass, "%s", pass);
            snprintf(cfg.api_url, sizeof cfg.api_url, "%s", api_url);
            snprintf(cfg.device_id, sizeof cfg.device_id, "%s", dev);
            snprintf(cfg.api_key, sizeof cfg.api_key, "%s", key);
            cfg.enabled = true;
            autobrain::wifi_cfg_save(cfg, prefs);
            // F2: consume the token — the same value can never be replayed.
            // Also clear the characteristic value (hygiene; Fw1 + window gate
            // it anyway).
            _token[0] = '\0';
            _provTokenChar->setValue("");
            Serial.printf("BLE provisioning saved (ssid=%s dev=%s)\n",
                          cfg.ssid, cfg.device_id);
            _c->setValue((uint8_t*)"ok", 2);
        }
    private:
        NimBLECharacteristic* _c;
        char* _token;
        NimBLECharacteristic* _provTokenChar;
        uint32_t* _open_ms;
    };
};