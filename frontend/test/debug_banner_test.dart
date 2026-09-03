import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/core/config.dart';
import 'package:autobrain/core/debug_banner.dart';


void main() {
  testWidgets('DebugBanner shows API/WS in debug mode', (tester) async {
    AppConfig.apiBase = 'https://example.test/api/v1';
    AppConfig.wsBase = 'wss://example.test/ws';

    await tester.pumpWidget(
      const Directionality(
        textDirection: TextDirection.ltr,
        child: DebugBanner(child: SizedBox.shrink()),
      ),
    );

    final bannerFinder = find.byType(Banner);
    expect(bannerFinder, findsOneWidget,
        reason: 'Banner overlay should be present in debug mode');
    final banner = tester.widget<Banner>(bannerFinder);
    expect(banner.message, contains('https://example.test/api/v1'));
    expect(banner.message, contains('wss://example.test/ws'));
    expect(banner.location, BannerLocation.topEnd);
  });
}
