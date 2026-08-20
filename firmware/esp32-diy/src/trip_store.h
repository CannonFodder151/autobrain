#pragma once

#include <LittleFS.h>
#include "obd_pids.h"

// Trip capture to on-device LittleFS. Phone-dead requirement: everything is
// appended to flash locally; the app only pulls trips over BLE later.
// Layout: /trips/<UTC_STAMP>.csv  — one CSV per trip, header + rows.
// A small index file /trips/index.txt lists completed trips newest-first so
// the BLE sync layer and the app can enumerate without directory scans.
class TripStore {
public:
    bool begin() {
        if (!LittleFS.begin(true)) return false;
        if (!LittleFS.exists("/trips")) LittleFS.mkdir("/trips");
        _ok = true;
        return true;
    }

    bool beginTrip(const char* stamp) {
        if (!_ok) return false;
        char path[64];
        snprintf(path, sizeof path, "/trips/%s.csv", stamp);
        _file = LittleFS.open(path, FILE_APPEND);
        if (!_file) return false;
        _file.print(autobrain::trip_header());
        _active = true;
        return true;
    }

    bool appendRow(const char* row) {
        if (!_active) return false;
        _file.print(row);
        return true;
    }

    // Returns true if a trip was completed (so caller can bump the index).
    bool endTrip() {
        if (!_active) return false;
        _file.close();
        _active = false;
        return true;
    }

    void refreshIndex() {
        if (!_ok) return;
        File root = LittleFS.open("/trips");
        File f = root.openNextFile();
        String list;
        while (f) {
            if (!f.isDirectory()) {
                String name = f.name();
                if (name.endsWith(".csv")) list += name + "\n";
            }
            f = root.openNextFile();
        }
        File idx = LittleFS.open("/trips/index.txt", FILE_WRITE);
        if (idx) { idx.print(list); idx.close(); }
    }

    String index() {
        if (!_ok) return String();
        File idx = LittleFS.open("/trips/index.txt", "r");
        if (!idx) return String();
        String s = idx.readString();
        idx.close();
        return s;
    }

    size_t tripCount() {
        size_t n = 0;
        for (char* c = index().begin(); *c; c++) if (*c == '\n') n++;
        return n;
    }

    bool active() const { return _active; }

private:
    bool _ok = false;
    bool _active = false;
    File _file;
};
