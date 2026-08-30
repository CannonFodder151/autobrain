/// GPS speed source for the phone-side auto trip path (AUT-367).
///
/// The Android/iOS implementation streams speed (km/h) from the platform
/// geolocator; web/desktop get a no-op — the import below picks the IO
/// implementation only on platforms with `dart:io`, so the web build never
/// links the geolocator channel.
library;

import 'speed_source_stub.dart'
    if (dart.library.io) 'speed_source_io.dart' as impl;
import 'car_kit_trip_monitor.dart';

class SpeedSourceFactory {
  /// Creates the platform GPS speed source. No-op on web/desktop.
  static SpeedSource create() => impl.SpeedSourceImpl.create();
}
