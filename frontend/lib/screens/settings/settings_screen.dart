import 'dart:convert';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/download.dart';
import '../../widgets/responsive.dart';
import 'car_integration_screen.dart';

String _errorText(Object e) => e is ApiException ? e.message : '$e';

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

  bool get _aiEnabled => !((_profile?['free_account'] as bool?) ?? false);
  bool get _obdEnabled => (_profile?['obd_enabled'] as bool?) ?? false;
  int get _maxVehicles => (_profile?['max_vehicles'] as int?) ?? 1;
  int get _vehiclesUsed => (_profile?['vehicle_count'] as int?) ?? 0;

  Widget _chip(bool on) => Chip(
        label: Text(on ? 'Enabled' : 'Disabled'),
        visualDensity: VisualDensity.compact,
        backgroundColor:
            on ? Colors.green.withOpacity(0.15) : Colors.grey.withOpacity(0.15),
        side: BorderSide(
          color: on ? Colors.green : Colors.grey,
          width: 1,
        ),
        labelStyle: TextStyle(
            color: on ? Colors.green.shade700 : Colors.grey, fontSize: 12),
      );

  Widget _countChip(int used, int max) => Chip(
        label: Text('$used/$max'),
        visualDensity: VisualDensity.compact,
        backgroundColor: Colors.blue.withOpacity(0.15),
        side: BorderSide(color: Colors.blue, width: 1),
        labelStyle: TextStyle(color: Colors.blue.shade700, fontSize: 12),
      );

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
    } catch (e) {
      debugPrint('SettingsScreen._load failed: ${e.runtimeType}: $e');
    }
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
      debugPrint('SettingsScreen._beginSetup failed: ${e.runtimeType}: $e');
      setState(() => _error = _errorText(e));
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
      debugPrint('SettingsScreen._enable failed: ${e.runtimeType}: $e');
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
      debugPrint('SettingsScreen._disable failed: ${e.runtimeType}: $e');
      setState(() => _error = 'Invalid code — try again');
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
      debugPrint('SettingsScreen._export failed: ${e.runtimeType}: $e');
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Export failed: ${_errorText(e)}')));
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
            content: Text('Profile restored — your vehicles and records were replaced.')));
      }
    } catch (e) {
      debugPrint('SettingsScreen._import failed: ${e.runtimeType}: $e');
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Restore failed: ${_errorText(e)}')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.read<AuthState>();
    return Scaffold(
      appBar: AppBar(title: const Text('Settings & security')),
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 800),
          child: ListView(
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
                          autofillHints: const [AutofillHints.oneTimeCode],
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
                            autofillHints: const [AutofillHints.oneTimeCode],
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
          Text('Account features',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          Card(
            child: Column(
              children: [
                ListTile(
                  leading: Icon(_aiEnabled ? Icons.auto_awesome : Icons.auto_awesome_outlined,
                      color: _aiEnabled ? Colors.green : Colors.grey),
                  title: const Text('AI features'),
                  subtitle: Text(
                      _aiEnabled
                          ? 'Enabled — diagnostics, predictions, OCR, valuation'
                          : 'Disabled on this account'),
                  trailing: _chip(_aiEnabled),
                ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.directions_car),
                  title: const Text('Maximum cars'),
                  trailing: _countChip(_vehiclesUsed, _maxVehicles),
                ),
                const Divider(height: 1),
                if (!kIsWeb)
                  ListTile(
                    leading: Icon(_obdEnabled ? Icons.settings_input_component : Icons.settings_input_component_outlined,
                        color: _obdEnabled ? Colors.green : Colors.grey),
                    title: const Text('OBD features'),
                    subtitle: Text(
                        _obdEnabled
                            ? 'Enabled — Bluetooth adapter + fault codes'
                            : 'Disabled on this account'),
                    trailing: _chip(_obdEnabled),
                  ),
                const Divider(height: 1),
                ListTile(
                  leading: const Icon(Icons.verified_user_outlined),
                  title: const Text('Rego lookup'),
                  subtitle: Text(
                      _aiEnabled
                          ? 'Enabled — auto-fill vehicle details from an AU plate'
                          : 'Disabled on this account — upgrade to enable'),
                  trailing: _chip(_aiEnabled),
          ),
        ],
      ),
    ),
          const SizedBox(height: 16),
          if (!kIsWeb)
            Card(
              child: ListTile(
                leading: const Icon(Icons.car_repair_outlined),
                title: const Text('Car Play / Android Auto'),
                subtitle: const Text(
                    'Auto trip logging, connection status, platform limits'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () => Navigator.of(context).push(MaterialPageRoute(
                    builder: (_) => const CarIntegrationScreen())),
              ),
            ),
          const SizedBox(height: 16),
          Card(
            child: Column(
              children: [
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
                  title: const Text('Restore your profile'),
                  subtitle: const Text(
                      'Replace this account\'s vehicles and records from an '
                      'exported profile (overrides current data)'),
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
      ),
    ),
    );
  }
}
