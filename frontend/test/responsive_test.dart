// Tests for AUT-2526: responsive breakpoints and CenteredMaxWidth utility.
//
// The web app must cap content width on desktop (1100/1400) and pass through on
// mobile so the screens report in an audit don't stretch to 1920px.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/widgets/responsive.dart';

void main() {
  group('Breakpoints', () {
    test('desktop starts at 1100', () {
      expect(Breakpoints.desktop, 1100.0);
      expect(Breakpoints.wideDesktop, 1400.0);
      expect(Breakpoints.wideDesktop > Breakpoints.desktop, isTrue);
    });
  });

  group('CenteredMaxWidth', () {
    Widget host(Widget child, {required Size size}) {
      return MaterialApp(
        home: MediaQuery(
          data: MediaQueryData(size: size),
          child: Scaffold(body: CenteredMaxWidth(child: child)),
        ),
      );
    }

    testWidgets('passes through on mobile width (375)', (tester) async {
      tester.view.physicalSize = const Size(375, 667);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(host(const SizedBox(width: 100, height: 50),
          size: const Size(375, 667)));
      final sz = tester.getSize(find.byType(SizedBox));
      expect(sz.width, 100);
    });

    testWidgets('caps content width at Breakpoints.wideDesktop on 1920',
        (tester) async {
      tester.view.physicalSize = const Size(1920, 1080);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      await tester.pumpWidget(host(const SizedBox(width: 100, height: 50),
          size: const Size(1920, 1080)));
      // The ConstrainedBox wrapping the SizedBox should clamp to wideDesktop.
      final cbFinder = find.descendant(
        of: find.byType(CenteredMaxWidth),
        matching: find.byType(ConstrainedBox),
      );
      expect(cbFinder, findsOneWidget);
      final box = tester.widget<ConstrainedBox>(cbFinder);
      expect(box.constraints.maxWidth, Breakpoints.wideDesktop);
    });
  });
}
