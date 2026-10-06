/// Live network connectivity state, broadcast via ValueNotifier so any widget
/// can subscribe without re-creating a stream listener each time.
library;

import 'package:flutter/foundation.dart' show VoidCallback;
import 'package:connectivity_plus/connectivity_plus.dart';

// VoidCallback is in dart:ui, re-exported via flutter/foundation; add explicit
// import so dart2js web builds resolve it without relying on barrel resolution
// edge cases on the arm64 runner.
import 'package:flutter/foundation.dart';

/// Process-wide singleton. Widgets listen via [isOnline] or [addListener].
class ConnectivityService {
  ConnectivityService._();
  static final instance = ConnectivityService._();

  bool _online = true;
  bool get isOnline => _online;

  final Set<VoidCallback> _listeners = {};

  void addListener(VoidCallback cb) => _listeners.add(cb);
  void removeListener(VoidCallback cb) => _listeners.remove(cb);

  /// Initialises the service. The first connectivity probe is raced against a
  /// 3-second timeout so that a hung `checkConnectivity()` on web (where the
  /// Network Information API can be absent) never blocks `main()` past
  /// `runApp()`. Connectivity listeners are wired immediately so state stays
  /// correct once the platform plugin does resolve.
  Future<void> init() async {
    _check().timeout(const Duration(seconds: 3)).catchError((_) {});
    Connectivity().onConnectivityChanged.listen((_) => _check());
  }

  Future<void> check() => _check();

  Future<void> _check() async {
    final result = await Connectivity().checkConnectivity();
    final online = !result.contains(ConnectivityResult.none);
    if (online != _online) {
      _online = online;
      for (final cb in Set.of(_listeners)) {
        cb();
      }
    }
  }
}
