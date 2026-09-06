# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

> This is the single shared changelog for BOTH the hosted (web) app (`frontend/`)
> and the mobile app (`CannonFodder151/autobrain-mobile`). Every feature or
> user-facing change ships with an entry here under `[Unreleased]` — see
> `CONTRIBUTING.md` for the frontend-parity + changelog rules.


## [Unreleased]
### Added (AUT-2703)
- feat(firmware,backend,frontend): extend trip CSV row schema with EV/PHEV fields (`soc_pct,pack_v,pack_a,pack_temp_c,odo_km,ev_mode`) for AUT-2437. `format_trip_row` in `obd_pids.h` now emits 13-field rows (old 7-field rows still accepted via default args). CSV header updated to `epoch,rpm,speed,coolant,throttle,lat,lon,soc_pct,pack_v,pack_a,pack_temp_c,odo_km,ev_mode`. `csv_to_gps_json` (upload_payload.h), backend `parse_board_csv` (trip_gps.py), and frontend `tripCsvToJson` (dongle_relay.dart) all tolerate both old and new row lengths via fixed-position reads. Dart tests expanded with backward-compat + EV-field cases. C++ self_check expanded with EV-field assertions + old-format CSV tolerance.

### Added (AUT-2702)
- feat(firmware): EV manufacturer PID table + VIN decode stub. New header `firmware/esp32-diy/src/ev_pids.h` maps manufacturer VIN prefix (WMI) to Mode-22 PIDs (SOC%, pack V/I/temp) for GM, Nissan, Hyundai/Kia, Tesla, Rivian, Ford, BMW, Volkswagen, Toyota. Adds `build_mode22_request`, `is_valid_mode22_response`, `ev_decode_value`, `vin_wmi`, `ev_profile_for_wmi`. Stub in `main.cpp` (`select_ev_profile`, `pid_request_m22`, `ev_read_pack`) auto-selects profile on first trip; fallback is generic profile. Self-check assertions added in `test/self_check.cpp`.

### Fixed (AUT-2600)
- fix(frontend): add missing `child:` label on the `ConstrainedBox` wrapping `ListView.builder` in `vehicle_timeline_screen.dart` (line 60). The widget was passed as a positional argument, misaligning the formal argument list and tripping dart2js on every `ConstrainedBox` inside the body (the compile error attached to login_screen.dart / home_screen.dart / signup_screen.dart were the downstream effect). Closes the second-half of AUT-2600 (unblocks `build-hosted.yml` amd64+arm64 `flutter build web` for the AUT-2446 Replace + AUT-2447 Upgrade release).

### Fixed (AUT-2600)
- fix(frontend): Servo Spy map `_StationSheet` 30-day history button was wired to a dead method (`_openHistory(BuildContext)` defined inside `_ServoSpyListState`, which has no `station` field) and the Dart `web` compile failed with `Error: The getter 'station' isn't defined for type '_ServoSpyListState'`, blocking the dockerhub-publish `publish-arm64` / `publish-amd64` jobs (publish #1445 aborted, no new image, containers stale). Moved the navigation into `_StationSheet` (which has `this.station`) and removed the broken overload. List-view history navigation is unchanged.
