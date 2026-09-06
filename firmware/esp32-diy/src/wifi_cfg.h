#pragma once

#include <Preferences.h>

// WiFi upload configuration (AUT-918), stored in NVS so it survives deep
// sleep and reboot. Provisioned once over BLE from the app (see ble_sync.h):
//   ssid, pass  = home/garage WiFi (WPA2/3-PSK, 2.4 GHz)
//   api_url     = backend base, e.g. https://hosted.autobrainservice.app/api/v1
//   device_id   = the AutoBrain `devices` row id
//   api_key     = the per-device key (shown once in the app)
//   vin         = vehicle VIN for EV profile selection (AUT-2706)
namespace autobrain {

inline const char* WIFI_CFG_NAMESPACE = "wifi";

struct WifiCfg {
    char ssid[33];       // 32 + NUL
    char pass[64];
    char api_url[128];
    char device_id[40];
    char api_key[80];
    char vin[18];        // AUT-2706: VIN for EV profile selection (17 + NUL)
    bool enabled = false;
};

inline void wifi_cfg_load(WifiCfg& cfg, Preferences& prefs) {
    memset(&cfg, 0, sizeof cfg);
    prefs.begin(WIFI_CFG_NAMESPACE, true);  // read-only first
    prefs.getString("ssid", cfg.ssid, sizeof cfg.ssid);
    prefs.getString("pass", cfg.pass, sizeof cfg.pass);
    prefs.getString("api_url", cfg.api_url, sizeof cfg.api_url);
    prefs.getString("device_id", cfg.device_id, sizeof cfg.device_id);
    prefs.getString("api_key", cfg.api_key, sizeof cfg.api_key);
    prefs.getString("vin", cfg.vin, sizeof cfg.vin);
    cfg.enabled = prefs.getBool("enabled", false);
    prefs.end();
    cfg.enabled = cfg.enabled && cfg.ssid[0] && cfg.device_id[0] && cfg.api_key[0];
}

inline bool wifi_cfg_save(WifiCfg& cfg, Preferences& prefs) {
    prefs.begin(WIFI_CFG_NAMESPACE, false);
    prefs.putString("ssid", cfg.ssid);
    prefs.putString("pass", cfg.pass);
    prefs.putString("api_url", cfg.api_url);
    prefs.putString("device_id", cfg.device_id);
    prefs.putString("api_key", cfg.api_key);
    prefs.putString("vin", cfg.vin);
    prefs.putBool("enabled", cfg.enabled);
    prefs.end();
    return true;
}

inline void wifi_cfg_clear(Preferences& prefs) {
    prefs.begin(WIFI_CFG_NAMESPACE, false);
    prefs.clear();
    prefs.end();
}

}  // namespace autobrain