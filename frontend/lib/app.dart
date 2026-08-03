import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'core/auth_state.dart';
import 'core/theme.dart';
import 'screens/auth/login_screen.dart';
import 'screens/auth/reset_password.dart';
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

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    final resetToken = resetTokenFromUrl();

    Widget home;
    if (resetToken != null) {
      home = ResetPasswordScreen(token: resetToken);
    } else {
      home = auth.isLoggedIn ? const HomeScreen() : const LoginScreen();
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
