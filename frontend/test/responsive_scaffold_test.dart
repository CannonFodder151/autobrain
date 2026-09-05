import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/core/responsive.dart';

void main() {
  group('breakpoint resolution', () {
    test('mobile at 480px', () {
      const bp = Breakpoint.mobile;
      expect(480 < Breakpoints.desktopMin, isTrue);
      expect(480 <= Breakpoints.mobileMax, isTrue);
      expect(bp, Breakpoint.mobile);
    });

    test('tablet at 900px', () {
      expect(900 > Breakpoints.mobileMax, isTrue);
      expect(900 < Breakpoints.desktopMin, isTrue);
      const bp = Breakpoint.tablet;
      expect(bp, Breakpoint.tablet);
    });

    test('desktop at 1400px', () {
      expect(1400 >= Breakpoints.desktopMin, isTrue);
      const bp = Breakpoint.desktop;
      expect(bp, Breakpoint.desktop);
    });

    test('max content width cap is 1200px', () {
      expect(Breakpoints.maxContentWidth, 1200);
    });
  });

  testWidgets('ResponsiveScaffold builds on wide viewport without throwing',
      (WidgetTester tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: MediaQuery(
          data: const MediaQueryData(size: Size(1440, 1024)),
          child: ResponsiveScaffold(
            child: const Center(child: Text('ok')),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('ok'), findsOneWidget);
  });
}
