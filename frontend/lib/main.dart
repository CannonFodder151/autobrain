import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app.dart';
import 'core/auth_state.dart';
import 'core/config.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await AppConfig.load();
  runApp(
    ChangeNotifierProvider(
      create: (_) => AuthState(),
      child: const AutoBrainApp(),
    ),
  );
}
