/// Geolocator-backed GPS speed source for the phone-side auto trip path
/// (AUT-367). Streams speed in km/h from the platform position stream; null
/// speed (stationary/GPS fixing) is filtered out.
library;

import 'dart:async';

import 'package:geolocator/geolocator.dart';

import 'car_kit_trip_monitor.dart';

class SpeedSourceImpl {
  static SpeedSource create() => _GeolocatorSpeedSource();

  static const int distanceFilterMeters = 0;
  static const Duration interval = Duration(seconds: 1);
}

class _GeolocatorSpeedSource implements SpeedSource {
  @override
  Stream<double> get speedKmh {
    final stream = Geolocator.getPositionStream(
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.best,
        distanceFilter: SpeedSourceImpl.distanceFilterMeters,
        timeLimit: null,
      ),
    );
    return stream
        .where((p) => p.speed != null && p.speed >= 0)
        .map((p) => p.speed! * 3.6); // m/s → km/h
  }
}
