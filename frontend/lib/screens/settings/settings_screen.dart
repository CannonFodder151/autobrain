import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/download.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  Map<String, dynamic>? _profile;
  Map<String, dynamic>? _setup; // {secret, otpauth_url, qr_data_url}
  final _code = TextEditingController();
  bool _busy = false;
  bool _mfaEnabled = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    try {
      final me = await api.get('/auth/me') as Map<String, dynamic>;
      setState(() {
        _profile = me;
        _mfaEnabled = me['mfa_enabled'] == true;
      });
    } catch (_) {}
  }

  Future<void> _beginSetup() async {
    final api = context.read<AuthState>().api;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final data = await api.get('/auth/mfa/setup') as Map<String, dynamic>;
      setState(() => _setup = data);
    } catch (e) {
      setState(() => _error = '$e');
    } finally {
      setState(() => _busy = false);
    }
  }

  Future<void> _enable() async {
    final api = context.read<AuthState>().api;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await api.post('/auth/mfa/enable', {'code': _code.text.trim()});
      setState(() {
        _setup = null;
        _code.clear();
        _mfaEnabled = true;
      });
    } catch (e) {
      setState(() => _error = 'Invalid code — try again');
    } finally {
      setState(() => _busy = false);
    }
  }

  Future<void> _disable() async {
    final api = context.read<AuthState>().api;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await api.post('/auth/mfa/disable', {'code': _code.text.trim()});
      setState(() {
        _code.clear();
        _mfaEnabled = false;
      });
    } catch (e) {
      setState(() => _error = 'Invalid code — try again');
    } finally {
      setState(() => _busy = false);
    }
  }

  Future<void> _toggleFree(bool v) async {
    final api = context.read<AuthState>().api;
    setState(() => _busy = true);
    try {
      await api.patch('/auth/settings', {'free_account': v});
      await _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    } finally {
      setState(() => _busy = false);
    }
  }

  Future<void> _export() async {
    final api = context.read<AuthState>().api;
    try {
      final bytes = await api.export('/auth/export');
      await downloadBytes('autobrain-profile.json', bytes);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Export failed: $e')));
      }
    }
  }

  Future<void> _import() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['json'],
    );
    if (result == null || result.files.isEmpty) return;
    final picked = result.files.single;
    final List<int> bytes;
    if (picked.bytes != null) {
      bytes = picked.bytes!;
    } else if (picked.path != null) {
      bytes = await readLocalFile(picked.path!);
    } else {
      return;
    }
    final api = context.read<AuthState>().api;
    try {
      await api.upload('/auth/import', bytes, picked.name, 'application/json');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('Profile imported. Sign in with the imported account.')));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Import failed: $e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.read<AuthState>();
    return Scaffold(
      appBar: AppBar(title: const Text('Settings & security')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: ListTile(
              leading: const Icon(Icons.person),
              title: Text(_profile?['display_name'] ?? 'Loading…'),
              subtitle: Text(_profile?['email'] ?? ''),
              trailing: _profile?['role'] == 'admin'
                  ? const Chip(label: Text('Admin'), visualDensity: VisualDensity.compact)
                  : null,
            ),
          ),
          const SizedBox(height: 16),
          Text('Two-factor authentication (MFA)',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: _mfaEnabled
                  ? Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Row(
                          children: [
                            Icon(Icons.verified_user, color: Colors.green),
                            SizedBox(width: 8),
                            Text('MFA is enabled',
                                style: TextStyle(fontWeight: FontWeight.w600)),
                          ],
                        ),
                        const SizedBox(height: 12),
                        TextField(
                          controller: _code,
                          keyboardType: TextInputType.number,
                          maxLength: 6,
                          decoration: const InputDecoration(
                            labelText: 'Current code to disable',
                            counterText: '',
                          ),
                        ),
                        const SizedBox(height: 8),
                        FilledButton.tonal(
                          onPressed: _busy ? null : _disable,
                          child: const Text('Disable MFA'),
                        ),
                      ],
                    )
                  : Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Protect your account with an authenticator app '
                            '(Google Authenticator, Authy, 1Password, …).'),
                        const SizedBox(height: 12),
                        if (_setup != null) ...[
                          ClipRRect(
                            borderRadius: BorderRadius.circular(12),
                            child: Image.memory(
                              base64Decode(_setup!['qr_data_url']
                                  .toString()
                                  .split(',')
                                  .last),
                              width: 180,
                              height: 180,
                            ),
                          ),
                          const SizedBox(height: 12),
                          SelectableText(
                            'Manual key: ${_setup!['secret']}',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                          const SizedBox(height: 12),
                          TextField(
                            controller: _code,
                            keyboardType: TextInputType.number,
                            maxLength: 6,
                            autofocus: true,
                            decoration: const InputDecoration(
                              labelText: 'Enter 6-digit code',
                              counterText: '',
                            ),
                          ),
                          const SizedBox(height: 8),
                          FilledButton(
                            onPressed: _busy ? null : _enable,
                            child: const Text('Enable MFA'),
                          ),
                        ] else
                          FilledButton.tonalIcon(
                            onPressed: _busy ? null : _beginSetup,
                            icon: const Icon(Icons.qr_code),
                            label: const Text('Set up MFA'),
                          ),
                      ],
                    ),
            ),
          ),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text(_error!,
                  style: TextStyle(color: Colors.red.shade600)),
            ),
          const SizedBox(height: 16),
          Text('Account plan & data',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          Card(
            child: Column(
              children: [
                SwitchListTile(
                  title: const Text('Free account'),
                  subtitle: const Text(
                      'Free tier disables AI features, file exports and rego '
                      'lookup. Upgrade to enable them.'),
                  value: (_profile?['free_account'] as bool?) ?? false,
                  onChanged: _toggleFree,
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.download),
                  title: const Text('Export my data'),
                  subtitle: const Text(
                      'Download your full profile (vehicles, history, logbook) '
                      'as a JSON file'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: _export,
                ),
                ListTile(
                  leading: const Icon(Icons.upload_file),
                  title: const Text('Import a profile'),
                  subtitle: const Text(
                      'Load a previously exported profile onto this server'),
                  trailing: const Icon(Icons.chevron_right),
                  onTap: _import,
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Card(
            child: ListTile(
              leading: const Icon(Icons.info_outline),
              title: const Text('Account'),
              subtitle: Text('Signed in as ${auth.isAdmin ? 'administrator' : 'user'}'),
            ),
          ),
        ],
      ),
    );
  }
}
