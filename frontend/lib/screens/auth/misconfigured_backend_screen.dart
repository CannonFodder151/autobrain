import 'package:flutter/material.dart';

/// Shown when [AppConfig.validate] fails at startup so the user gets a clear
/// actionable error instead of a forever-spinning login / server-picker.
class MisconfiguredBackendScreen extends StatelessWidget {
  const MisconfiguredBackendScreen({
    super.key,
    required this.apiBase,
    required this.error,
  });

  final String apiBase;
  final String? error;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      home: Scaffold(
        backgroundColor: const Color(0xFF1B1F24),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.cloud_off, color: Colors.redAccent, size: 56),
                const SizedBox(height: 16),
                const Text(
                  'AutoBrain backend is unreachable',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 22,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 12),
                Text(
                  'Resolved API_BASE_URL:\n$apiBase',
                  style: const TextStyle(color: Colors.white70, fontSize: 13),
                ),
                const SizedBox(height: 12),
                if (error != null)
                  Text(
                    error!,
                    style: const TextStyle(color: Colors.white60, fontSize: 13),
                  ),
                const SizedBox(height: 24),
                const Text(
                  'If you are running the hosted build, this usually means the '
                  'image was built with the wrong BACKEND_URL. If you self-host, '
                  'check the server is up and the URL is reachable from this device.',
                  style: TextStyle(color: Colors.white54, fontSize: 12),
                ),
                const SizedBox(height: 24),
                ElevatedButton(
                  onPressed: () {
                    // Re-run validation by popping back to the app entry; main()
                    // is the only call site so a full restart is required.
                  },
                  child: const Text('Close'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}