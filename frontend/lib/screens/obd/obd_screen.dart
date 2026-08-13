import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../core/auth_state.dart';
import '../../core/models.dart';
import '../../services/obd/obd_connection.dart';
import '../../services/obd/obd_trip_monitor.dart';
import '../diagnostics/add_diagnostic_screen.dart';

/// OBD-II integration.
///
/// Live Bluetooth adapter features work here: connect to an ELM327 adapter
/// (Bluetooth Classic SPP, e.g. VGate iCar Pro), read the fault codes from the
/// car, and poll live PID data. When auto-connect is on, an automatic trip
/// recorder (GoFar-style) starts/stops logbook trips from ignition signals
/// while the app is backgrounded — see `ObdTripMonitor`.
class ObdScreen extends StatefulWidget {
  const ObdScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<ObdScreen> createState() => _ObdScreenState();
}

class _ObdScreenState extends State<ObdScreen> {
  final ObdTripMonitor _monitor = ObdTripMonitor.instance;

  List<ObdCode> _codes = const [];
  bool _enabled = false;
  bool _autoConnect = false;
  bool _loading = true;
  String? _vin;
  bool _updatingVin = false;

  @override
  void initState() {
    super.initState();
    _monitor.addListener(_onMonitorChanged);
    _load();
    _monitor.arm(widget.vehicleId);
  }

  @override
  void dispose() {
    _monitor.removeListener(_onMonitorChanged);
    super.dispose();
  }

  bool _wasConnected = false;

  void _onMonitorChanged() {
    if (!mounted) return;
    final connected = _monitor.connection.isConnected;
    if (connected && !_wasConnected) _syncFromAdapter();
    _wasConnected = connected;
    setState(() {});
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
        _vin = vehicle['vin'] as String?;
      });
      // Persist the OBD flags so the background trip monitor can gate on them
      // without a network call.
      final prefs = await SharedPreferences.getInstance();
      await prefs.setBool('obd_enabled', _enabled);
      await prefs.setBool('obd_auto_connect', _autoConnect);
      _monitor.setEnabled(_enabled);
      _monitor.setAutoConnect(_autoConnect);
      _monitor.arm(widget.vehicleId);
    } catch (_) {}
    setState(() => _loading = false);
  }

  Future<void> _toggleConnect(bool v) async {
    setState(() => _autoConnect = v);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('obd_auto_connect', v);
    _monitor.setAutoConnect(v);
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
      final devices = await _monitor.connection.bondedDevices();
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
      if (selected != null) await _monitor.connect(selected);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  Future<void> _disconnect() async {
    await _monitor.disconnect();
  }

  /// After a fresh connect the monitor owns live-PID learning, live readings
  /// and auto-trip recording. This hook is intentionally a no-op today:
  /// VIN writes are manual-only (AUT-361) so nothing is auto-written here.
  Future<void> _syncFromAdapter() async {}

  Future<void> _readFaultCodes() async {
    final session = _monitor.connection.session;
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
                hintText: '17-character VIN of this vehicle'),
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

  /// Manual "Update VIN" button: reads the VIN over OBD (mode 09 PID 02) and
  /// updates the vehicle record — only after explicit user confirmation.
  Future<void> _updateVin() async {
    final session = _monitor.connection.session;
    if (session == null) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
          content: Text('Connect the OBD adapter first, then update the VIN.')));
      return;
    }
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Update VIN?'),
        content: const Text(
            'Read the VIN from the connected OBD adapter and replace the '
            'stored VIN for this vehicle?'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Read & update')),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    setState(() => _updatingVin = true);
    final messenger = ScaffoldMessenger.of(context);
    final api = context.read<AuthState>().api;
    try {
      final vin = await updateVin(session, (v) =>
          api.post('/vehicles/${widget.vehicleId}/obd/vin', {'vin': v}));
      messenger.showSnackBar(
          SnackBar(content: Text('VIN $vin saved from adapter')));
      await _load();
    } catch (e) {
      messenger.showSnackBar(
          SnackBar(content: Text('Could not update VIN: $e')));
    } finally {
      if (mounted) setState(() => _updatingVin = false);
    }
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

  /// Clears the saved fault-code library (not the car). Confirmed before run.
  Future<void> _clearSavedCodes() async {
    final api = context.read<AuthState>().api;
    final messenger = ScaffoldMessenger.of(context);
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Clear saved codes?'),
        content: const Text(
            'This removes every saved fault code for this vehicle from the '
            'app. Codes still stored in the car are not affected.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Clear')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await api.delete('/vehicles/${widget.vehicleId}/obd/codes');
      _load();
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('$e')));
    }
  }

  /// Clears the car's ECU DTCs (mode 04) via the adapter, then re-reads.
  Future<void> _clearCarCodes() async {
    final session = _monitor.connection.session;
    if (session == null) return;
    final messenger = ScaffoldMessenger.of(context);
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Clear codes from car?'),
        content: const Text(
            'This asks the ECU to erase its stored fault codes. Saved codes '
            'in the app library are not affected.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Clear')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await session.clearDtc();
      messenger.showSnackBar(
          const SnackBar(content: Text('Fault codes cleared')));
      await _readFaultCodes();
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text('$e')));
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
    final status = _monitor.connection.status;
    if (status == ObdStatus.connected) {
      final live = _monitor.live;
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
                    child: Text(
                        'Connected · ${_monitor.connection.adapterLabel}',
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
              if (live.isNotEmpty)
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final r in live)
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
                  const SizedBox(width: 8),
                  IconButton(
                    tooltip: 'Clear codes from car',
                    onPressed: _clearCarCodes,
                    icon: const Icon(Icons.delete_sweep),
                  ),
                ],
              ),
            ],
          ),
        ),
      );
    }
    final error = _monitor.connection.error;
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

  Widget _autoTripCard() {
    final recorder = _monitor.recorder;
    final active = recorder.activeTrip;
    final pending = recorder.pending.length;
    final String status;
    final IconData icon;
    final Color color;
    if (active != null) {
      status = 'Recording trip since '
          '${_fmtTime(active.startedAt)} — appears in the logbook when the '
          'car turns off.';
      icon = Icons.route;
      color = Colors.green;
    } else if (pending > 0) {
      status = '$pending trip${pending == 1 ? '' : 's'} waiting to sync to '
          'the logbook (will upload when the server is reachable).';
      icon = Icons.cloud_upload_outlined;
      color = Colors.orange;
    } else {
      status = 'Automatic trips are recorded while the adapter is connected '
          'and appear in the logbook marked "auto (OBD)".';
      icon = Icons.auto_awesome;
      color = Colors.grey;
    }
    return Card(
      child: ListTile(
        leading: Icon(icon, color: color),
        title: const Text('Automatic trip recording'),
        subtitle: Text(status),
      ),
    );
  }

  String _fmtTime(DateTime t) {
    final h = t.hour.toString().padLeft(2, '0');
    final m = t.minute.toString().padLeft(2, '0');
    return '$h:$m';
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
                            'Connect to the adapter automatically and record '
                            'trips while the app is in the background'),
                        value: _autoConnect,
                        onChanged: _toggleConnect,
                      ),
                      const SizedBox(height: 8),
                      _autoTripCard(),
                      const SizedBox(height: 8),
                      Card(
                        child: ListTile(
                          leading: const Icon(Icons.settings_ethernet),
                          title: const Text('Vehicle VIN'),
                          subtitle: Text(
                            (_vin == null || _vin!.isEmpty)
                                ? 'Not set. Read it from the OBD adapter or enter it manually.'
                                : _vin!,
                          ),
                          trailing: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              TextButton(
                                  onPressed: _setVin,
                                  child: const Text('Set VIN')),
                              if (_updatingVin)
                                const Padding(
                                  padding: EdgeInsets.all(8),
                                  child: SizedBox(
                                    width: 18,
                                    height: 18,
                                    child: CircularProgressIndicator(
                                        strokeWidth: 2),
                                  ),
                                )
                              else
                                TextButton(
                                    onPressed: _updateVin,
                                    child: const Text('Update VIN')),
                            ],
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),
                      Row(
                        children: [
                          Text('Fault codes',
                              style: Theme.of(context).textTheme.titleMedium),
                          const Spacer(),
                          if (_codes.isNotEmpty)
                            IconButton(
                              tooltip: 'Clear saved codes',
                              onPressed: _clearSavedCodes,
                              icon: const Icon(Icons.delete_sweep),
                            ),
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
