/// PassKey management screen.
///
/// Lists the user's registered passkeys, allows registering a new one, and
/// deleting existing ones. Only available on web (where WebAuthn is supported).
library;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';

class PasskeyManagementScreen extends StatefulWidget {
  const PasskeyManagementScreen({super.key});

  @override
  State<PasskeyManagementScreen> createState() =>
      _PasskeyManagementScreenState();
}

class _PasskeyManagementScreenState extends State<PasskeyManagementScreen> {
  List<Map<String, dynamic>>? _passkeys;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    final passkeys = await context.read<AuthState>().listPasskeys();
    if (!mounted) return;
    setState(() {
      _passkeys = passkeys;
      _loading = false;
    });
  }

  Future<void> _addPasskey() async {
    final nameController = TextEditingController();
    final result = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Add a passkey'),
        content: TextField(
          controller: nameController,
          decoration: const InputDecoration(
            labelText: 'Passkey name',
            hintText: 'e.g. Chrome on MacBook',
          ),
          autofocus: true,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(nameController.text),
            child: const Text('Register'),
          ),
        ],
      ),
    );

    if (result == null || result.isEmpty) return;

    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Registering passkey...')),
    );

    final ok = await context.read<AuthState>().registerPasskey(result);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(ok ? 'Passkey registered' : 'Failed to register passkey'),
      ),
    );
    if (ok) _load();
  }

  Future<void> _deletePasskey(String credentialId, String label) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete passkey?'),
        content: Text(
          'Delete "$label"? You will no longer be able to sign in with this passkey.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            style: FilledButton.styleFrom(backgroundColor: Colors.red),
            child: const Text('Delete'),
          ),
        ],
      ),
    );

    if (confirm != true) return;

    final ok = await context.read<AuthState>().deletePasskey(credentialId);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(ok ? 'Passkey deleted' : 'Failed to delete passkey'),
      ),
    );
    if (ok) _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Passkeys')),
      body: SafeArea(
        child: Column(
          children: [
            if (!kIsWeb)
              const Padding(
                padding: EdgeInsets.all(24),
                child: Text(
                  'PassKey sign-in is only available on the web version of AutoBrain.',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: Colors.grey),
                ),
              )
            else if (_loading)
              const Expanded(
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_error != null)
              Expanded(
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          _error!,
                          textAlign: TextAlign.center,
                          style: TextStyle(color: Colors.red.shade600),
                        ),
                        const SizedBox(height: 16),
                        FilledButton.tonal(
                          onPressed: _load,
                          child: const Text('Retry'),
                        ),
                      ],
                    ),
                  ),
                ),
              )
            else if (_passkeys == null || _passkeys!.isEmpty)
              Expanded(
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          Icons.fingerprint,
                          size: 48,
                          color: Theme.of(context).colorScheme.primary.withOpacity(0.5),
                        ),
                        const SizedBox(height: 16),
                        const Text(
                          'No passkeys registered yet',
                          style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
                        ),
                        const SizedBox(height: 8),
                        const Text(
                          'Passkeys let you sign in with your fingerprint, '
                          'face scan, or security key — no password needed.',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: Colors.grey),
                        ),
                      ],
                    ),
                  ),
                ),
              )
            else
              Expanded(
                child: RefreshIndicator(
                  onRefresh: _load,
                  child: ListView.separated(
                    padding: const EdgeInsets.symmetric(vertical: 8),
                    itemCount: _passkeys!.length,
                    separatorBuilder: (_, __) => const Divider(height: 1),
                    itemBuilder: (context, index) {
                      final pk = _passkeys![index];
                      final label = pk['label'] as String? ?? 'Passkey';
                      final deviceType = pk['device_type'] as String? ?? 'unknown';
                      final createdAt = pk['created_at'] as String?;
                      final lastUsed = pk['last_used_at'] as String?;
                      final credentialId = pk['credential_id'] as String;

                      return ListTile(
                        leading: Icon(
                          deviceType == 'platform'
                              ? Icons.phone_iphone
                              : Icons.security,
                        ),
                        title: Text(label),
                        subtitle: Text(
                          [
                            if (createdAt != null) 'Created: ${_formatDate(createdAt)}',
                            if (lastUsed != null) 'Last used: ${_formatDate(lastUsed)}',
                            if (lastUsed == null) 'Never used',
                          ].join(' · '),
                          style: const TextStyle(fontSize: 12),
                        ),
                        trailing: IconButton(
                          icon: const Icon(Icons.delete_outline, color: Colors.red),
                          onPressed: () => _deletePasskey(credentialId, label),
                        ),
                      );
                    },
                  ),
                ),
              ),
          ],
        ),
      ),
      floatingActionButton: kIsWeb && (_passkeys?.isNotEmpty ?? false)
          ? FloatingActionButton(
              onPressed: _addPasskey,
              child: const Icon(Icons.add),
            )
          : null,
    );
  }

  static String _formatDate(String iso) {
    try {
      final dt = DateTime.parse(iso);
      return '${dt.day}/${dt.month}/${dt.year}';
    } catch (_) {
      return iso;
    }
  }
}
