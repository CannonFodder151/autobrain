/// Car-kit / head-unit Bluetooth connection source for the phone-side auto
/// trip path (AUT-367).
///
/// The Android implementation listens to ACL connect/disconnect broadcasts for
/// bonded devices (a head-unit or car-kit), delivered over a platform channel.
/// Web/desktop get a no-op — the import below picks the IO implementation only
/// on platforms with `dart:io`, so the web build never links the channel.
library;

import 'car_kit_connection_stub.dart'
    if (dart.library.io) 'car_kit_connection_io.dart' as impl;
import 'car_kit_trip_monitor.dart';

class CarKitConnectionSource {
  /// Creates the platform car-kit connection source. No-op on web/desktop.
  static CarKitConnection create() => impl.CarKitConnectionImpl.create();
}
