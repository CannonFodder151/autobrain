import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';

class ConnectivityService with ChangeNotifier {
  ConnectivityService._() {
    _subscription = Connectivity().onConnectivityChanged.listen(_onChange);
    _checkInitial();
  }

  static final ConnectivityService instance = ConnectivityService._();

  final Connectivity _connectivity = Connectivity();
  StreamSubscription<List<ConnectivityResult>>? _subscription;

  final ValueNotifier<bool> isOnline = ValueNotifier<bool>(true);

  Future<void> _checkInitial() async {
    final result = await _connectivity.checkConnectivity();
    _update(result);
  }

  void _onChange(List<ConnectivityResult> results) {
    _update(results);
  }

  void _update(List<ConnectivityResult> results) {
    final online = results.any((r) => r != ConnectivityResult.none);
    final changed = isOnline.value != online;
    if (changed) {
      isOnline.value = online;
      notifyListeners();
    }
  }

  Future<void> disposeAsync() async {
    await _subscription?.cancel();
  }
}
