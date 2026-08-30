/// Android EventChannel-backed car-kit connection source (AUT-367).
///
/// Subscribes to the [CarKitChannel.EVENT_CHANNEL] event channel that the
/// native MainActivity feeds from Bluetooth ACL connect/disconnect broadcasts.
/// `connected`/`disconnected` strings map to [CarKitLinkState].
library;

import 'dart:async';

import 'package:flutter/services.dart';

import 'car_kit_trip_monitor.dart';

class CarKitConnectionImpl {
  static CarKitConnection create() => _EventChannelConnection();

  static const String channelName = 'autobrain/car_kit_connection';
}

class _EventChannelConnection implements CarKitConnection {
  @override
  Stream<CarKitLinkState> get stateChanges {
    const channel = EventChannel(CarKitConnectionImpl.channelName);
    return channel
        .receiveBroadcastStream()
        .where((e) => e is String)
        .map((e) => e == 'connected'
            ? CarKitLinkState.connected
            : CarKitLinkState.disconnected);
  }
}
