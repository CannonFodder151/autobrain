import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'core/auth_state.dart';
import 'core/config.dart';
import 'core/theme.dart';
import 'screens/auth/login_screen.dart';
import 'screens/auth/reset_password.dart';
import 'screens/auth/server_setup_screen.dart';
import 'screens/auth/signup_screen.dart';
import 'screens/home/home_screen.dart';

class AutoBrainApp extends StatelessWidget {
  const AutoBrainApp({super.key});

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

  /// True when opened from a website "Get started" button
  /// (…/?signup=1) — routes a logged-out user straight to account creation.
  static bool signupRequested() {
    final uri = Uri.base;
    return uri.queryParameters['signup'] == '1' ||
        uri.pathSegments.contains('signup');
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    final resetToken = resetTokenFromUrl();

    Widget home;
    if (resetToken != null) {
      home = ResetPasswordScreen(token: resetToken);
    } else if (!AppConfig.serverConfigured) {
      home = const ServerSetupScreen();
    } else if (auth.isLoggedIn) {
      home = const HomeScreen();
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
