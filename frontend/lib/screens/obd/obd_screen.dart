import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/models.dart';
import '../../services/obd/elm327.dart';
import '../../services/obd/obd_connection.dart';
import '../diagnostics/add_diagnostic_screen.dart';

/// OBD-II integration.
///
/// Live Bluetooth adapter features work here: connect to an ELM327 adapter
/// (Bluetooth Classic SPP, e.g. VGate iCar Pro), read the VIN and fault codes
/// from the car, and poll live PID data. The codes library and "diagnose with
/// AI" save/read through the backend.
class ObdScreen extends StatefulWidget {
  const ObdScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<ObdScreen> createState() => _ObdScreenState();
}

class _ObdScreenState extends State<ObdScreen> {
  final ObdConnection _connection = ObdConnection();

  List<ObdCode> _codes = const [];
  bool _enabled = false;
  bool _autoConnect = false;
  bool _loading = true;
  bool _vinMissing = false;
  Set<String>? _supported;
  List<PidReading> _live = const [];
  Timer? _poll;

  @override
  void initState() {
    super.initState();
    _connection.addListener(_onConnectionChanged);
    _load();
  }

  @override
  void dispose() {
    _poll?.cancel();
    _connection.removeListener(_onConnectionChanged);
    _connection.disconnect();
    super.dispose();
  }

  void _onConnectionChanged() {
    if (!mounted) return;
    setState(() {});
    if (_connection.isConnected) {
      _poll ??= Timer.periodic(const Duration(seconds: 2), (_) => _pollLive());
      _syncFromAdapter();
    } else {
      _poll?.cancel();
      _poll = null;
      setState(() => _live = const []);
    }
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    setState(() => _loading = true);
    try {
      final settings = await api
          .get('/vehicles/${widget.vehicleId}/obd/settings') as Map<String, dynamic>;
      final codes = await api
              .get('/vehicles/${widget.vehicleId}/obd/codes') as List;
      final vehicle =
          await api.get('/vehicles/${widget.vehicleId}') as Map<String, dynamic>;
      setState(() {
        _enabled = (settings['enabled'] as bool?) ?? false;
        _autoConnect = (settings['auto_connect'] as bool?) ?? false;
        _codes = codes
            .map((e) => ObdCode.fromJson(e as Map<String, dynamic>))
            .toList();
        final vin = vehicle['vin'] as String?;
        _vinMissing = vin == null || vin.length < 5;
      });
      if (_autoConnect && _connection.status == ObdStatus.off) {
        _autoConnectToSaved();
      }
    } catch (_) {}
    setState(() => _loading = false);
  }

  Future<void> _autoConnectToSaved() async {
    final adapter = await _connection.lastAdapter();
    if (adapter == null) return;
    _connect(adapter);
  }

  Future<void> _toggleConnect(bool v) async {
    setState(() => _autoConnect = v);
    try {
      await context
          .read<AuthState>()
          .api
          .patch('/auth/settings', {'obd_auto_connect': v});
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  Future<void> _pickAdapter() async {
    try {
      final devices = await _connection.bondedDevices();
      if (!mounted) return;
      if (devices.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('No paired Bluetooth devices. Pair the OBD adapter '
                'in system settings first.')));
        return;
      }
      final selected = await showModalBottomSheet<ObdAdapter>(
        context: context,
        builder: (ctx) => SafeArea(
          child: ListView(
            shrinkWrap: true,
            children: [
              const ListTile(
                title: Text('Paired Bluetooth devices'),
                subtitle: Text('Pick the ELM327 OBD adapter'),
              ),
              for (final d in devices)
                ListTile(
                  leading: const Icon(Icons.bluetooth),
                  title: Text(d.label),
                  subtitle: Text(d.address),
                  onTap: () => Navigator.pop(ctx, d),
                ),
            ],
          ),
        ),
      );
      if (selected != null) await _connect(selected);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  Future<void> _connect(ObdAdapter adapter) async {
    try {
      await _connection.connect(adapter);
    } catch (_) {}
  }

  Future<void> _disconnect() async {
    await _connection.disconnect();
  }

  /// After a fresh connect: learn supported PIDs, autofill a missing VIN,
  /// and pull any stored fault codes into the library.
  Future<void> _syncFromAdapter() async {
    final session = _connection.session;
    if (session == null) return;
    final api = context.read<AuthState>().api;
    try {
      final supported = await session.readSupportedPids();
      if (mounted) setState(() => _supported = supported);
    } catch (_) {}
    if (_vinMissing) {
      try {
        final vin = await session.readVin();
        await api.post('/vehicles/${widget.vehicleId}/obd/vin', {'vin': vin});
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(content: Text('VIN $vin saved from adapter')));
        }
        await _load();
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
              content: Text('Could not read VIN from adapter: $e')));
        }
      }
    }
  }

  Future<void> _pollLive() async {
    final session = _connection.session;
    if (session == null) return;
    try {
      final readings = await session.readLive(supported: _supported);
      if (mounted && _connection.isConnected) setState(() => _live = readings);
    } catch (_) {}
  }

  Future<void> _readFaultCodes() async {
    final session = _connection.session;
    if (session == null) return;
    final messenger = ScaffoldMessenger.of(context);
    final api = context.read<AuthState>().api;
    try {
      final dtcs = await session.readDtc();
      final existing = _codes.map((c) => c.code).toSet();
      var added = 0;
      for (final d in dtcs) {
        if (existing.contains(d.code)) continue;
        try {
          await api.post('/vehicles/${widget.vehicleId}/obd/codes',
              {'code': d.code, 'description': d.description, 'source': 'obd'});
          added++;
        } catch (_) {}
      }
      messenger.showSnackBar(SnackBar(
          content: Text(added == 0
              ? 'No new fault codes from adapter'
              : 'Saved $added fault code${added == 1 ? '' : 's'} from adapter')));
      await _load();
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('$e')));
    }
  }

  Future<void> _setVin() async {
    final vc = TextEditingController();
    final formKey = GlobalKey<FormState>();
    final api = context.read<AuthState>().api;
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Enter VIN'),
        content: Form(
          key: formKey,
          child: TextFormField(
            controller: vc,
            decoration: const InputDecoration(
                labelText: 'VIN',
                hintText:
                    'Auto-populated from the OBD adapter on first connect'),
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
            onPressed: () async {
              if (vc.text.trim().length < 5) return;
              try {
                await api.post('/vehicles/${widget.vehicleId}/obd/vin',
                    {'vin': vc.text.trim()});
                if (ctx.mounted) Navigator.pop(ctx);
                _load();
              } catch (e) {
                if (ctx.mounted) {
                  ScaffoldMessenger.of(ctx)
                      .showSnackBar(SnackBar(content: Text('$e')));
                }
              }
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
  }

  Future<void> _addCode() async {
    final cc = TextEditingController();
    final dc = TextEditingController();
    final api = context.read<AuthState>().api;
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Add OBD fault code'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: cc,
              decoration: const InputDecoration(
                  labelText: 'Code', hintText: 'e.g. P0301'),
            ),
            const SizedBox(height: 8),
            TextField(
              controller: dc,
              decoration: const InputDecoration(labelText: 'Description (optional)'),
            ),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
            onPressed: () async {
              final code = cc.text.trim().toUpperCase();
              if (code.isEmpty) return;
              try {
                await api.post('/vehicles/${widget.vehicleId}/obd/codes', {
                  'code': code,
                  'description': dc.text.isEmpty ? null : dc.text,
                  'source': 'manual',
                });
                if (ctx.mounted) Navigator.pop(ctx);
                _load();
              } catch (e) {
                if (ctx.mounted) {
                  ScaffoldMessenger.of(ctx)
                      .showSnackBar(SnackBar(content: Text('$e')));
                }
              }
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
  }

  Future<void> _deleteCode(ObdCode c) async {
    try {
      await context
          .read<AuthState>()
          .api
          .delete('/vehicles/${widget.vehicleId}/obd/codes/${c.id}');
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  Future<void> _diagnoseCodes(List<String> codes) async {
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => AddDiagnosticScreen(
            vehicleId: widget.vehicleId, initialCodes: codes),
      ),
    );
  }

  Widget _adapterCard() {
    final status = _connection.status;
    if (status == ObdStatus.connected) {
      return Card(
        color: Theme.of(context).colorScheme.surfaceContainerHighest,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(Icons.bluetooth_connected, color: Colors.green),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text('Connected · ${_connection.adapterLabel}',
                        style: Theme.of(context).textTheme.titleSmall),
                  ),
                  IconButton(
                    tooltip: 'Disconnect',
                    onPressed: _disconnect,
                    icon: const Icon(Icons.link_off),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              if (_live.isNotEmpty)
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final r in _live)
                      Chip(
                        label: Text(r.label,
                            style: const TextStyle(fontSize: 12)),
                      ),
                  ],
                )
              else
                const Text('Reading live data…',
                    style: TextStyle(color: Colors.grey)),
              const SizedBox(height: 8),
              Row(
                children: [
                  FilledButton.tonalIcon(
                    onPressed: _readFaultCodes,
                    icon: const Icon(Icons.warning_amber),
                    label: const Text('Read fault codes'),
                  ),
                ],
              ),
            ],
          ),
        ),
      );
    }
    final error = _connection.error;
    return Card(
      child: Column(
        children: [
          if (error != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              child: Row(
                children: [
                  const Icon(Icons.error_outline, color: Colors.red),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(error,
                        style: const TextStyle(color: Colors.red)),
                  ),
                ],
              ),
            ),
          Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Icon(
                  status == ObdStatus.connecting
                      ? Icons.bluetooth_searching
                      : Icons.bluetooth_disabled,
                  color: status == ObdStatus.connecting
                      ? Colors.orange
                      : Colors.grey,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    status == ObdStatus.connecting
                        ? 'Connecting to adapter…'
                        : 'Connect a Bluetooth ELM327 adapter to read live '
                            'vehicle data (VIN, fault codes, live PIDs).',
                    style: TextStyle(
                        color: status == ObdStatus.connecting
                            ? null
                            : Colors.grey),
                  ),
                ),
                if (status != ObdStatus.connecting)
                  FilledButton.tonalIcon(
                    onPressed: _pickAdapter,
                    icon: const Icon(Icons.bluetooth),
                    label: const Text('Connect'),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('OBD port')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : !_enabled
              ? const Center(
                  child: Padding(
                    padding: EdgeInsets.all(24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.lock_outline, size: 48, color: Colors.grey),
                        SizedBox(height: 12),
                        Text(
                          'OBD access is not enabled for this account.\n'
                          'Contact your administrator to enable it.',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: Colors.grey),
                        ),
                      ],
                    ),
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(
                    padding: const EdgeInsets.all(16),
                    children: [
                      _adapterCard(),
                      const SizedBox(height: 12),
                      SwitchListTile(
                        title: const Text('Auto-connect OBD via Bluetooth'),
                        subtitle: const Text(
                            'Connect to the adapter automatically when the app opens'),
                        value: _autoConnect,
                        onChanged: _toggleConnect,
                      ),
                      const SizedBox(height: 8),
                      if (_vinMissing)
                        Card(
                          child: ListTile(
                            leading:
                                const Icon(Icons.settings_ethernet),
                            title: const Text('VIN missing'),
                            subtitle: const Text(
                                'Auto-populated from the OBD adapter on first connect.'),
                            trailing: TextButton(
                              onPressed: _setVin,
                              child: const Text('Set VIN'),
                            ),
                          ),
                        ),
                      const SizedBox(height: 16),
                      Row(
                        children: [
                          Text('Fault codes',
                              style: Theme.of(context).textTheme.titleMedium),
                          const Spacer(),
                          FilledButton.tonalIcon(
                            onPressed: _addCode,
                            icon: const Icon(Icons.add),
                            label: const Text('Add code'),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      if (_codes.isEmpty)
                        const Text('No fault codes saved yet.',
                            style: TextStyle(color: Colors.grey))
                      else
                        for (final c in _codes)
                          Card(
                            child: ListTile(
                              leading: Icon(
                                c.isResolved
                                    ? Icons.check_circle
                                    : Icons.error_outline,
                                color: c.isResolved
                                    ? Colors.green
                                    : Colors.orange,
                              ),
                              title: Text(c.code,
                                  style: const TextStyle(
                                      fontWeight: FontWeight.bold)),
                              subtitle: Text(c.description ?? c.source),
                              trailing: PopupMenuButton<String>(
                                onSelected: (v) {
                                  if (v == 'diagnose') {
                                    _diagnoseCodes([c.code]);
                                  }
                                  if (v == 'delete') _deleteCode(c);
                                },
                                itemBuilder: (_) => const [
                                  PopupMenuItem(
                                      value: 'diagnose',
                                      child: Text('Diagnose with AI')),
                                  PopupMenuItem(
                                      value: 'delete', child: Text('Delete')),
                                ],
                              ),
                            ),
                          ),
                      if (_codes.isNotEmpty) ...[
                        const SizedBox(height: 12),
                        FilledButton.tonalIcon(
                          onPressed: () =>
                              _diagnoseCodes(_codes.map((c) => c.code).toList()),
                          icon: const Icon(Icons.smart_toy),
                          label: const Text('Diagnose all codes with AI'),
                        ),
                      ],
                    ],
                  ),
                ),
    );
  }
}
