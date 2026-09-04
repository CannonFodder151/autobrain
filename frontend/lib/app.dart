import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'core/auth_state.dart';
import 'core/config.dart';
import 'core/theme.dart';
import 'core/models.dart';
import 'community_garage/screens/share_link_view.dart';
import 'screens/advisor/overview_screen.dart';
import 'screens/auth/login_screen.dart';
import 'screens/auth/reset_password.dart';
import 'screens/auth/server_setup_screen.dart';
import 'screens/auth/signup_screen.dart';
import 'screens/home/home_screen.dart';
import 'screens/settings/license_screen.dart';

class AutoBrainApp extends StatelessWidget {
  const AutoBrainApp({super.key});

  /// Deep-link fragment captured at startup, before the Flutter web engine
  /// normalizes the URL (clears `#/license` via `history.replaceState`
  /// within ~2-4s of load). Without this, the logged-in rebuild reads an
  /// already-cleared fragment and Home mounts instead of License. Set once
  /// from `main()`; null falls back to the live `Uri.base.fragment`.
  static String? initialFragment;

  /// True when the app was opened from a password-reset email link
  /// (…/reset-password#token=…) — fragment kept out of query logs/history.
  static String? resetTokenFromUrl() {
    final uri = Uri.base;
    if (uri.pathSegments.isEmpty || uri.pathSegments.last != 'reset-password') return null;
    return _fragmentToken(uri.fragment) ?? uri.queryParameters['token'];
  }

  static String? _fragmentToken(String frag) {
    if (frag.isEmpty) return null;
    for (final part in frag.split('&')) {
      final kv = part.split('=');
      if (kv.length == 2 && kv[0] == 'token' && kv[1].isNotEmpty) return Uri.decodeComponent(kv[1]);
    }
    return null;
  }

  /// True when opened from a shared-build deep link — routes to the Community
  /// Garage share viewer. Accepts `{origin}/s/{token}` (design) and the
  /// server-relative `{origin}/social/share/{token}` forms.
  static String? shareTokenFromUrl() {
    final segs = Uri.base.pathSegments;
    if (segs.length >= 2 && segs.last == 's') {
      return Uri.base.queryParameters['token'] ?? segs[segs.length - 2];
    }
    if (segs.length >= 3 &&
        segs[segs.length - 3] == 'social' &&
        segs[segs.length - 2] == 'share') {
      return segs.last;
    }
    return null;
  }

  /// True when opened from a website "Get started" button
  /// (…/?signup=1) — routes a logged-out user straight to account creation.
  static bool signupRequested() {
    final uri = Uri.base;
    return uri.queryParameters['signup'] == '1' ||
        uri.pathSegments.contains('signup');
  }

  /// True when opened from the mobile app's License link
  /// ({origin}/#/license) — routes a logged-in user to the License screen so
  /// purchases happen in the browser, not in the store-published app.
  static bool licenseRequested() {
    final fragment =
        (initialFragment ?? Uri.base.fragment).replaceAll('/', '').toLowerCase();
    return fragment == 'license';
  }

  /// Maps an Ownership Advisor deep-link path token to the Overview tab
  /// index. Tokens outside the closed set fall through to the default
  /// Overview tab.
  static int? advisorTabFromUrl() {
    final segs = Uri.base.pathSegments;
    if (segs.isEmpty || segs.first != 'advisor') return null;
    if (segs.length == 1) return 0;
    switch (segs[1]) {
      case 'value':
        return 1;
      case 'replace':
        return 2;
      case 'upgrade':
        return 3;
      case 'finance':
        return 4;
      case 'dream':
        return 5;
      case 'ai':
        return 6;
      default:
        return 0;
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    final resetToken = resetTokenFromUrl();
    final shareToken = shareTokenFromUrl();
    final advisorTab = advisorTabFromUrl();

    Widget home;
    if (resetToken != null) {
      home = ResetPasswordScreen(token: resetToken);
    } else if (!AppConfig.serverConfigured) {
      home = const ServerSetupScreen();
    } else if (shareToken != null) {
      home = ShareLinkView(token: shareToken);
    } else if (auth.isLoggedIn) {
      if (licenseRequested()) {
        home = const LicenseScreen();
      } else if (advisorTab != null) {
        home = _AdvisorDeepLink(tabIndex: advisorTab);
      } else {
        home = const HomeScreen();
      }
    } else if (signupRequested() && auth.signupEnabled) {
      home = const SignupScreen();
    } else {
      home = const LoginScreen();
    }

    return MaterialApp(
      title: 'AutoBrain',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      themeMode: auth.darkMode ? ThemeMode.dark : ThemeMode.light,
      home: home,
      builder: (context, child) {
        // Visible under debug AND profile mode so performance testers can
        // confirm the resolved API base + boot-probe result without
        // attaching DevTools. (AUT-2284 N2.) Never shown in release.
        if (!(kDebugMode || kProfileMode)) return child!;
        final ok = AppConfig.lastValidationOk;
        final validation = ok == null
            ? 'not run'
            : ok
                ? 'ok'
                : 'fail';
        final apiHost = Uri.tryParse(AppConfig.apiBase)?.host ?? AppConfig.apiBase;
        return Stack(
          children: [
            child!,
            Positioned(
              left: 0,
              right: 0,
              top: 0,
              child: SafeArea(
                bottom: false,
                child: Container(
                  width: double.infinity,
                  color: Colors.black.withValues(alpha: 0.55),
                  padding: const EdgeInsets.symmetric(
                      horizontal: 8, vertical: 2),
                  child: Text(
                    'api: $apiHost  probe: $validation',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 11,
                      fontFamily: 'monospace',
                    ),
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

/// Renders the Ownership Advisor for the user's current vehicle at the
/// tab matching a `/advisor/{value|replace|upgrade|finance|dream|ai}`
/// deep-link. Falls back to the Overview tab if no vehicle is selected.
class _AdvisorDeepLink extends StatefulWidget {
  const _AdvisorDeepLink({required this.tabIndex});
  final int tabIndex;

  @override
  State<_AdvisorDeepLink> createState() => _AdvisorDeepLinkState();
}

class _AdvisorDeepLinkState extends State<_AdvisorDeepLink> {
  Vehicle? _vehicle;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final auth = context.read<AuthState>();
    try {
      final data = await auth.api.get('/vehicles') as List;
      final vehicles = data
          .map((e) => Vehicle.fromJson(e as Map<String, dynamic>))
          .toList();
      if (!mounted) return;
      setState(() {
        _vehicle = Vehicle.resolveSelection(vehicles, null);
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }
    if (_vehicle == null) {
      return const HomeScreen();
    }
    return AdvisorOverviewScreen(
      vehicleId: _vehicle!.id,
      initialTabIndex: widget.tabIndex,
    );
  }
}
