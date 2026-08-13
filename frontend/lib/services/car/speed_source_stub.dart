/// No-op GPS speed source for platforms without a geolocation stream
/// (web/desktop). See [speed_source_io.dart] for Android/iOS.
library;

import 'dart:async';

import 'car_kit_trip_monitor.dart';

class SpeedSourceImpl {
  static SpeedSource create() => const _NoopSpeed();

  static const String channelName = 'autobrain/speed';
}

class _NoopSpeed implements SpeedSource {
  const _NoopSpeed();

  @override
  Stream<double> get speedKmh => const Stream.empty();
}
