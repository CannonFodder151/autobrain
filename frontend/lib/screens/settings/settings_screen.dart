import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';

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
