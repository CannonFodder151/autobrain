import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'core/auth_state.dart';
import 'core/config.dart';
import 'core/theme.dart';
import 'community_garage/screens/share_link_view.dart';
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
  /// (…/reset-password?token=…).
  static String? resetTokenFromUrl() {
    final uri = Uri.base;
    if (uri.pathSegments.isNotEmpty &&
        uri.pathSegments.last == 'reset-password') {
      return uri.queryParameters['token'];
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

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    final resetToken = resetTokenFromUrl();
    final shareToken = shareTokenFromUrl();

    Widget home;
    if (resetToken != null) {
      home = ResetPasswordScreen(token: resetToken);
    } else if (!AppConfig.serverConfigured) {
      home = const ServerSetupScreen();
    } else if (shareToken != null) {
      home = ShareLinkView(token: shareToken);
    } else if (auth.isLoggedIn) {
      home = licenseRequested() ? const LicenseScreen() : const HomeScreen();
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
    );
  }
}
