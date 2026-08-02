import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app.dart';
import 'core/auth_state.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(
    ChangeNotifierProvider(
      create: (_) => AuthState(),
      child: const AutoBrainApp(),
    ),
  );
}
