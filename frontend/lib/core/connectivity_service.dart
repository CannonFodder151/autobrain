/// Live network connectivity state, broadcast via ValueNotifier so any widget
/// can subscribe without re-creating a stream listener each time.
library;

import 'package:flutter/foundation.dart' show VoidCallback;
import 'package:connectivity_plus/connectivity_plus.dart';

/// Process-wide singleton. Widgets listen via [isOnline] or [addListener].
class ConnectivityService {
  ConnectivityService._();
  static final instance = ConnectivityService._();

  bool _online = true;
  bool get isOnline => _online;

  final Set<VoidCallback> _listeners = {};

  void addListener(VoidCallback cb) => _listeners.add(cb);
  void removeListener(VoidCallback cb) => _listeners.remove(cb);

  Future<void> init() async {
    await _check();
    Connectivity.instance.onConnectivityChanged.listen((_) => _check());
  }

  Future<void> _check() async {
    final result = await Connectivity().checkConnectivity();
    final online = result != ConnectivityResult.none;
    if (online != _online) {
      _online = online;
      for (final cb in Set.of(_listeners)) {
        cb();
      }
    }
  }
}
