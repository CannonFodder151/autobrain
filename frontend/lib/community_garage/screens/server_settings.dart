/// Admin server settings for Community Garage (AUT-332): feature + federation
/// toggles, server identity, hub registration status.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../social_api.dart';

class ServerSettings extends StatefulWidget {
  const ServerSettings({super.key});

  @override
  State<ServerSettings> createState() => _ServerSettingsState();
}

class _ServerSettingsState extends State<ServerSettings> {
  SocialSettings? _cfg;
  bool _loading = true;
  bool _saving = false;
  String? _error;
  final _serverName = TextEditingController();
  final _serverEmail = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _serverName.dispose();
    _serverEmail.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final cfg = await SocialApi(context.read<AuthState>().api).settings();
      _serverName.text = cfg.serverName ?? '';
      _serverEmail.text = cfg.serverEmail ?? '';
      if (mounted) setState(() => _cfg = cfg);
    } catch (e) {
      if (mounted) setState(() => _error = 'Could not load settings: $e');
    }
    setState(() => _loading = false);
  }

  Future<void> _save({bool? featureEnabled, bool? federationEnabled}) async {
    setState(() => _saving = true);
    try {
      final cfg = await SocialApi(context.read<AuthState>().api).updateSettings(
        featureEnabled: featureEnabled,
        federationEnabled: federationEnabled,
        serverName: _serverName.text.trim().isEmpty
            ? null
            : _serverName.text.trim(),
        serverEmail: _serverEmail.text.trim().isEmpty
            ? null
            : _serverEmail.text.trim(),
      );
      if (mounted) {
        setState(() => _cfg = cfg);
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Settings saved')));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Save failed: $e')));
      }
    }
    setState(() => _saving = false);
  }

  Future<void> _register() async {
    setState(() => _saving = true);
    try {
      final result = await SocialApi(context.read<AuthState>().api)
          .registerWithHub();
      if (mounted) {
        setState(() {
          _cfg = SocialSettings(
            featureEnabled: _cfg?.featureEnabled ?? true,
            federationEnabled: _cfg?.federationEnabled ?? false,
            serverName: result['server_name'] as String? ?? _serverName.text,
            serverEmail: _serverEmail.text,
            hubStatus: result['hub_status'] as String?,
            hubServerId: result['hub_server_id'] as String?,
          );
        });
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Registered with the federation hub')));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Registration failed: $e')));
      }
    }
    setState(() => _saving = false);
  }

  Future<void> _unregister() async {
    setState(() => _saving = true);
    try {
      await SocialApi(context.read<AuthState>().api).unregisterFromHub();
      if (mounted) {
        setState(() {
          _cfg = SocialSettings(
            featureEnabled: _cfg?.featureEnabled ?? true,
            federationEnabled: _cfg?.federationEnabled ?? false,
            serverName: _serverName.text,
            serverEmail: _serverEmail.text,
            hubStatus: 'unregistered',
          );
        });
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Unregistered from the hub')));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Unregister failed: $e')));
      }
    }
    setState(() => _saving = false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Community Garage settings')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(_error!, textAlign: TextAlign.center),
                        const SizedBox(height: 12),
                        FilledButton(
                            onPressed: _load, child: const Text('Retry')),
                      ],
                    ),
                  ),
                )
              : _cfg == null
                  ? const Center(child: Text('No settings'))
                  : ListView(
                      padding: const EdgeInsets.all(16),
                      children: [
                        SwitchListTile(
                          title: const Text('Community Garage enabled'),
                          subtitle: const Text(
                              'Off hides the feed and shows "Disabled by your admin".'),
                          value: _cfg!.featureEnabled,
                          onChanged: _saving
                              ? null
                              : (v) => _save(featureEnabled: v),
                        ),
                        SwitchListTile(
                          title: const Text('Federated participation'),
                          subtitle: const Text(
                              'Off = local-only feed. On = share + receive builds via the hub.'),
                          value: _cfg!.federationEnabled,
                          onChanged: _saving
                              ? null
                              : (v) => _save(federationEnabled: v),
                        ),
                        const Divider(height: 32),
                        Text('Server identity',
                            style: Theme.of(context).textTheme.titleMedium),
                        const SizedBox(height: 8),
                        TextField(
                          controller: _serverName,
                          decoration: const InputDecoration(
                            labelText: 'Server name',
                            border: OutlineInputBorder(),
                            helperText: 'Shown as the author server on shared builds.',
                          ),
                        ),
                        const SizedBox(height: 12),
                        TextField(
                          controller: _serverEmail,
                          keyboardType: TextInputType.emailAddress,
                          decoration: const InputDecoration(
                            labelText: 'Server contact email',
                            border: OutlineInputBorder(),
                          ),
                        ),
                        const SizedBox(height: 12),
                        Align(
                          alignment: Alignment.centerLeft,
                          child: FilledButton.tonal(
                            onPressed: _saving ? null : () => _save(),
                            child: const Text('Save identity'),
                          ),
                        ),
                        const Divider(height: 32),
                        Text('Federation hub',
                            style: Theme.of(context).textTheme.titleMedium),
                        const SizedBox(height: 8),
                        _hubStatusCard(),
                      ],
                    ),
    );
  }

  Widget _hubStatusCard() {
    final scheme = Theme.of(context).colorScheme;
    final status = _cfg!.hubStatus ?? 'unregistered';
    final color = status == 'registered'
        ? Colors.green
        : status == 'pending'
            ? Colors.amber
            : status == 'error'
                ? Colors.red
                : scheme.onSurfaceVariant;
    return Card(
      child: ListTile(
        leading: Icon(Icons.hub, color: color),
        title: Text('Hub status: $status'),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (_cfg!.hubServerId != null)
              Text('Server ID: ${_cfg!.hubServerId}'),
            if (_cfg!.hubUrl != null)
              Text('Hub: ${_cfg!.hubUrl}',
                  overflow: TextOverflow.ellipsis),
            if (status == 'pending')
              const Text(
                  'Registration pending hub-operator approval. The hub must '
                  'approve this server before builds are exchanged.')
            else if (!_cfg!.registered)
              const Text('Register to federate builds with other servers.'),
          ],
        ),
        trailing: _cfg!.registered
            ? OutlinedButton(
                onPressed: _saving ? null : _unregister,
                child: const Text('Unregister'),
              )
            : status == 'pending'
                ? OutlinedButton(
                    onPressed: _saving ? null : _load,
                    child: const Text('Refresh'),
                  )
                : FilledButton(
                    onPressed: _saving ? null : _register,
                    child: const Text('Register'),
                  ),
      ),
    );
  }
}
