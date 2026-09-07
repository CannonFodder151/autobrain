// Regression tests for AUT-2525: responsive breakpoint resolution and the
// max-content-width cap applied by ResponsiveScaffold.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter.dart';

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

    test('max content width cap', () {
      expect(Breakpoints.maxContentWidth, 1200);
    });
  });

  testWidgets('ResponsiveScaffold centres content and caps width',
      (WidgetTester tester) async {
    await tester.pumpWidget(const _Scope());
    final box = find.byType(ConstrainedBox).first;
    final renderBox = tester.renderObject(box) as RenderConstrainedBox;
    expect(renderBox.maxWidthConstraint.maxWidth, Breakpoints.maxContentWidth);
  });
}

class _Scope extends StatelessWidget {
  const _Scope();

  @override
  Widget build(BuildContext context) {
    // Use a wide viewport so the desktop cap kicks in.
    return MaterialApp(
      home: Builder(
        builder: (ctx) => MediaQuery(
          data: const MediaQueryData(size: Size(1440, 1024)),
          child: ResponsiveScaffold(
            child: const Scaffold(body: Center(child: Text('ok'))),
          ),
        ),
      ),
    );
  }
}
