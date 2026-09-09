import 'package:flutter/material.dart';

import 'config.dart';

/// Mounted in `main.dart` when `AppConfig.validate()` reports the configured
/// backend is unreachable in release builds. Surfaces a human-readable
/// reason and a Retry button that re-runs the probe + re-routes the app
/// to the normal home on success.
class MisconfiguredBackendScreen extends StatefulWidget {
  const MisconfiguredBackendScreen({super.key});

  @override
  State<MisconfiguredBackendScreen> createState() =>
      _MisconfiguredBackendScreenState();
}

class _MisconfiguredBackendScreenState extends State<MisconfiguredBackendScreen> {
  bool _retrying = false;

  Future<void> _retry() async {
    setState(() => _retrying = true);
    await AppConfig.validate();
    if (!mounted) return;
    if (AppConfig.lastValidationOk == true) {
      // Validation now passes — let main.dart's normal flow take over.
      // pushAndRemoveUntil replaces this route so the user can't navigate
      // back to the error screen (AUT-2272 M2).
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute<void>(builder: (_) => const _RetryHomeStub()),
        (_) => false,
      );
    } else {
      setState(() => _retrying = false);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            AppConfig.lastValidationError ?? 'Backend still unreachable',
          ),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final reason = AppConfig.lastValidationError ?? 'unknown reason';
    return Scaffold(
      appBar: AppBar(title: const Text('Backend unreachable')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Icon(Icons.cloud_off, size: 64),
              const SizedBox(height: 16),
              const Text(
                "We can't reach the AutoBrain backend",
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w600),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 12),
              SelectableText(
                'URL: ${AppConfig.apiBase}\nError: $reason',
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 13),
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
                label: Text(_retrying ? 'Rechecking…' : 'Retry'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Stub mounted by [_retry] when validation passes. main.dart's app shell
/// takes over on the next frame because the navigator is cleared.
class _RetryHomeStub extends StatelessWidget {
  const _RetryHomeStub();

  @override
  Widget build(BuildContext context) =>
      const Scaffold(body: Center(child: CircularProgressIndicator()));
}
