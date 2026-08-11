#pragma once

#include <NimBLEDevice.h>
#include "obd_pids.h"

// BLE service exposing trip data for the AutoBrain app to pull later.
// PoC scope: device advertises + exposes trip list over GATT. Full file
// transfer / pairing is the app-side sync phase.
// ponytail: one characteristic per trip would be cleaner, but for the PoC a
// single LIST characteristic + index file is enough; add file-transfer when
// the app sync client exists.
static const char* BLE_SERVICE_UUID  = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E";
static const char* BLE_CHAR_LIST_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E";

class BleSync {
public:
    void begin(const char* name) {
        NimBLEDevice::init(name);
        NimBLEServer* server = NimBLEDevice::createServer();
        NimBLEService* svc = server->createService(BLE_SERVICE_UUID);
        _list = svc->createCharacteristic(BLE_CHAR_LIST_UUID,
                                          NIMBLE_PROPERTY::READ | NIMBLE_PROPERTY::NOTIFY);
        svc->start();
        NimBLEAdvertising* adv = NimBLEDevice::getAdvertising();
        adv->addServiceUUID(BLE_SERVICE_UUID);
        adv->setName(name);
        adv->start();
    }

    void publishTrips(const String& index) {
        _list->setValue((uint8_t*)index.c_str(), index.length());
        _list->notify();
    }

private:
    NimBLECharacteristic* _list = nullptr;
};
