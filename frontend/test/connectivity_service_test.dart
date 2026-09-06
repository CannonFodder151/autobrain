import 'package:flutter_test/flutter_test.dart';
import 'package:autobrain/core/connectivity_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('singleton returns the same instance', () {
    final a = ConnectivityService.instance;
    final b = ConnectivityService.instance;
    expect(identical(a, b), isTrue);
  });

  test('isOnline ValueNotifier notifies listeners on change', () {
    final service = ConnectivityService.instance;
    final calls = <bool>[];
    final sub = service.isOnline.addListener(() => calls.add(service.isOnline.value));
    service.isOnline.value = false;
    service.isOnline.value = true;
    expect(calls, containsAllInOrder([false, true]));
    sub.cancel();
  });
}
