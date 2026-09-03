import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../app.dart';
import '../core/auth_state.dart';
import 'config.dart';

/// Shown when the configured BACKEND_URL is unreachable at boot
/// (AUT-2192). Single retry button that re-runs [AppConfig.validate].
class MisconfiguredBackendScreen extends StatefulWidget {
  const MisconfiguredBackendScreen({super.key});

  @override
  State<MisconfiguredBackendScreen> createState() => _MisconfiguredBackendScreenState();
}

class _MisconfiguredBackendScreenState extends State<MisconfiguredBackendScreen> {
  bool _retrying = false;

  Future<void> _retry() async {
    setState(() => _retrying = true);
    await AppConfig.validate();
    if (!mounted) return;
    setState(() => _retrying = false);
    if (AppConfig.lastValidationOk == true) {
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(
          builder: (_) => ChangeNotifierProvider(
            create: (_) => AuthState(),
            child: const AutoBrainApp(),
          ),
        ),
        (_) => false,
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      home: Scaffold(
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Icon(Icons.cloud_off, size: 72, color: Colors.redAccent),
                const SizedBox(height: 16),
                const Text(
                  'Backend unreachable',
                  style: TextStyle(fontSize: 22, fontWeight: FontWeight.w600),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 8),
                Text(
                  'Configured API base: ${AppConfig.apiBase}',
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontFamily: 'monospace'),
                ),
                const SizedBox(height: 8),
                Text(
                  AppConfig.lastValidationError ?? 'unknown error',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.grey.shade700),
                ),
                const SizedBox(height: 24),
                FilledButton.icon(
                  onPressed: _retrying ? null : _retry,
                  icon: _retrying
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.refresh),
                  label: Text(_retrying ? 'Retrying…' : 'Retry'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
