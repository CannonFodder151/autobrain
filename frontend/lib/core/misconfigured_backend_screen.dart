import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../app.dart';
import 'auth_state.dart';
import 'config.dart';
import 'responsive.dart';

/// Shown when the boot-time API probe fails (configured backend unreachable,
/// wrong URL, network down). Lets the user retry without bouncing them out
/// of the app, and surfaces the last error so QA / support can act on it.
class MisconfiguredBackendScreen extends StatefulWidget {
  const MisconfiguredBackendScreen({super.key});

  @override
  State<MisconfiguredBackendScreen> createState() =>
      _MisconfiguredBackendScreenState();
}

class _MisconfiguredBackendScreenState
    extends State<MisconfiguredBackendScreen> {
  bool _busy = false;

  Future<void> _retry() async {
    setState(() => _busy = true);
    await AppConfig.validate();
    if (!mounted) return;
    final ok = AppConfig.lastValidationOk == true;
    setState(() => _busy = false);
    if (!ok) return;
    // The root MaterialApp defines no `routes`/`onGenerateRoute` (autobrain
    // uses an `if/else` home switch in app.dart), so pushReplacementNamed('/')
    // throws `Could not find a generator for route RouteSettings("/")`.
    // Rebuild from the root instead so a successful retry actually leaves the
    // failure screen.
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(
        builder: (_) => ChangeNotifierProvider<AuthState>(
          create: (_) => AuthState(),
          child: const AutoBrainApp(),
        ),
      ),
      (_) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    final apiHost = Uri.tryParse(AppConfig.apiBase)?.host ?? AppConfig.apiBase;
    final err = AppConfig.lastValidationError ?? 'unknown error';
    return ResponsiveScaffold(
      child: Scaffold(
        appBar: AppBar(title: const Text('Backend unreachable')),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'AutoBrain could not reach the configured backend.',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 12),
              Text('Host: $apiHost'),
              const SizedBox(height: 8),
              Text('Error: $err'),
              const SizedBox(height: 24),
              FilledButton.icon(
                onPressed: _busy ? null : _retry,
                icon: _busy
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.refresh),
                label: const Text('Retry'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
