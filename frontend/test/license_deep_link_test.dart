// AUT-629: the Flutter web engine clears the `#/license` fragment within a few
// seconds of load, so the logged-in rebuild used to read an empty fragment and
// mount Home. The fragment is now captured once in main() before runApp and
// licenseRequested() reads that captured value.

import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/app.dart';

void main() {
  tearDown(() => AutoBrainApp.initialFragment = null);

  test('licenseRequested reads the fragment captured at startup', () {
    AutoBrainApp.initialFragment = '/license';
    expect(AutoBrainApp.licenseRequested(), isTrue);
  });

  test('licenseRequested false when no license fragment captured', () {
    AutoBrainApp.initialFragment = '';
    expect(AutoBrainApp.licenseRequested(), isFalse);
  });

  test('licenseRequested falls back to Uri.base when never captured', () {
    AutoBrainApp.initialFragment = null;
    expect(AutoBrainApp.licenseRequested(), isFalse);
  });
}
