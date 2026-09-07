import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'config.dart';

/// Debug-only build info overlay so QA/dev can confirm the resolved API/WS
/// base URL at app boot. Wrapped via [Banner] so it stays out of the layout
/// tree; the widget is a no-op in release/profile builds.
class DebugBanner extends StatelessWidget {
  const DebugBanner({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    if (!kDebugMode) return child;
    final api = AppConfig.apiBase;
    final ws = AppConfig.wsBase;
    return Banner(
      message: 'API: $api  WS: $ws',
      location: BannerLocation.topEnd,
      color: Colors.black.withValues(alpha: 0.55),
      child: child,
    );
  }
}
