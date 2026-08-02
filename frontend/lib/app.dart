import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'core/auth_state.dart';
import 'core/theme.dart';
import 'screens/auth/login_screen.dart';
import 'screens/home/home_screen.dart';

class AutoBrainApp extends StatelessWidget {
  const AutoBrainApp({super.key});

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    return MaterialApp(
      title: 'AutoBrain',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      darkTheme: AppTheme.dark(),
      home: auth.isLoggedIn ? const HomeScreen() : const LoginScreen(),
    );
  }
}
