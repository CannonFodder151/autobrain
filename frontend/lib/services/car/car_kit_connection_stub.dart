/// No-op car-kit connection source for platforms without a Bluetooth ACL
/// listener (web/desktop). See [car_kit_connection_io.dart] for Android.
library;

import 'dart:async';

import 'car_kit_trip_monitor.dart';

class CarKitConnectionImpl {
  static CarKitConnection create() => const _NoopConnection();

  static const String channelName = 'autobrain/car_kit_connection';
}

class _NoopConnection implements CarKitConnection {
  const _NoopConnection();

  @override
  Stream<CarKitLinkState> get stateChanges =>
      const Stream.empty();
}
