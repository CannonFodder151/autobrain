import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/config.dart';
import '../../core/models.dart';
import '../../services/dongle/dongle_ble.dart';
import '../../services/dongle/dongle_relay.dart';
import '../../services/dongle/dongle_settings.dart';
import '../../services/obd/obd_trip_monitor.dart';
import '../diagnostics/add_diagnostic_screen.dart';
import '../settings/dongle_wifi_panel.dart';

String _errorText(Object e) => e is ApiException ? e.message : '$e';

/// OBD fault-code library.
///
/// Generic ELM327/BT-SPP adapter support was removed (AUT-427) — the app only
/// supports the custom-built adapter. AUT-1573 adds that adapter back in
/// properly: BLE connect + trip sync + DTC read/clear, auto-connect on open,
/// plus the dongle WiFi settings moved here from Settings.
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
  bool _syncing = false;
  String? _adapterStatus;
  String? _bleId;
  DongleConfig _dongleCfg =
      const DongleConfig(enabled: false, ssid: '', pass: '');
  String? _vin;

  @override
  void initState() {
    super.initState();
    _load();
    _monitor.arm(widget.vehicleId);
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    setState(() => _loading = true);
    try {
      final settings =
          await api.get('/vehicles/${widget.vehicleId}/obd/settings')
              as Map<String, dynamic>;
      final codes =
          await api.get('/vehicles/${widget.vehicleId}/obd/codes') as List;
      final vehicle = await api.get('/vehicles/${widget.vehicleId}')
          as Map<String, dynamic>;
      final bleId = await DongleSettings.loadBleId();
      final dongleCfg = await DongleSettings.load();
      if (!mounted) return;
      setState(() {
        _enabled = (settings['enabled'] as bool?) ?? false;
        _autoConnect = (settings['auto_connect'] as bool?) ?? false;
        _codes = codes
            .map((e) => ObdCode.fromJson(e as Map<String, dynamic>))
            .toList();
        _vin = vehicle['vin'] as String?;
        _bleId = bleId;
        _dongleCfg = dongleCfg;
      });
      _monitor.arm(widget.vehicleId);
      // AUT-1573: auto-connect on open — silent best-effort sync.
      if (_autoConnect && _enabled && _bleId != null) {
        _connectAndSync(manual: false);
      }
    } catch (e) {
      debugPrint('ObdScreen._load failed: ${e.runtimeType}: $e');
    }
    setState(() => _loading = false);
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
                labelText: 'VIN', hintText: '17-character VIN of this vehicle'),
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
                debugPrint('ObdScreen._setVin failed: ${e.runtimeType}: $e');
                if (ctx.mounted) {
                  ScaffoldMessenger.of(ctx)
                      .showSnackBar(SnackBar(content: Text(_errorText(e))));
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
              decoration:
                  const InputDecoration(labelText: 'Description (optional)'),
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
                debugPrint('ObdScreen._addCode failed: ${e.runtimeType}: $e');
                if (ctx.mounted) {
                  ScaffoldMessenger.of(ctx)
                      .showSnackBar(SnackBar(content: Text(_errorText(e))));
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
      debugPrint('ObdScreen._deleteCode failed: ${e.runtimeType}: $e');
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(_errorText(e))));
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
      debugPrint('ObdScreen._clearSavedCodes failed: ${e.runtimeType}: $e');
      messenger.showSnackBar(SnackBar(content: Text(_errorText(e))));
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

  // ---------- Adapter connect / trip sync / DTC (AUT-1573) ----------

  Future<void> _setAutoConnect(bool value) async {
    final api = context.read<AuthState>().api;
    setState(() => _autoConnect = value);
    try {
      await api.patch('/auth/settings', {'obd_auto_connect': value});
    } catch (e) {
      debugPrint('ObdScreen._setAutoConnect failed: ${e.runtimeType}: $e');
      if (mounted) setState(() => _autoConnect = !value);
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(_errorText(e))));
      }
    }
  }

  String get _adapterLabel =>
      'AutoBrain OBD2 ESP32 adaptor (${_bleId ?? 'not paired'})';

  /// One BLE pass: pull trips + codes, relay trips to the server with the
  /// stored device key, and save any new fault codes into the vehicle's
  /// library. [manual] runs the pairing flow when no dongle is confirmed yet;
  /// auto-connect just reports that it needs one.
  Future<void> _connectAndSync({required bool manual}) async {
    if (_syncing) return;
    if (!DongleBle.supported) return;
    final api = context.read<AuthState>().api;
    var bleId = _bleId;
    if (bleId == null) {
      if (!manual) {
        setState(() => _adapterStatus =
            'Pair an adaptor once below to enable auto-connect.');
        return;
      }
      bleId = await _pairAdapter();
      if (bleId == null || !mounted) return;
      setState(() => _bleId = bleId);
    }
    setState(() {
      _syncing = true;
      _adapterStatus = 'Connecting…';
    });
    try {
      final result = await DongleBle.sync(bleId);
      if (!mounted) return;

      var relayed = '';
      if (result.trips.isNotEmpty) {
        setState(() => _adapterStatus =
            'Synced ${result.trips.length} trip(s) — uploading…');
        try {
          final r = await relayTrips(api,
              deviceId: _dongleCfg.deviceId ?? '', trips: result.trips);
          relayed = '${r.accepted} new, ${r.duplicates} duplicate(s)';
        } catch (e) {
          debugPrint('ObdScreen relay failed: ${e.runtimeType}: $e');
          relayed = 'upload failed';
        }
      }

      final saved = await _saveDeviceCodes(result.dtc);
      if (!mounted) return;
      setState(() {
        _adapterStatus = [
          if (result.trips.isNotEmpty)
            '${result.trips.length} trip(s): $relayed',
          if (saved > 0) '$saved new code(s) saved',
          if (result.trips.isEmpty && saved == 0 && result.dtc.isEmpty)
            'Connected — nothing new on the adaptor.',
        ].join(' · ');
        if (saved > 0) _load();
      });
    } catch (e) {
      debugPrint('ObdScreen._connectAndSync failed: ${e.runtimeType}: $e');
      if (mounted) setState(() => _adapterStatus = _errorText(e));
    } finally {
      if (mounted) setState(() => _syncing = false);
    }
  }

  /// Saves device-read DTC lines into the library (source "obd"), skipping
  /// codes already present in any source. Returns how many were new.
  Future<int> _saveDeviceCodes(String dtcText) async {
    final api = context.read<AuthState>().api;
    final known = _codes.map((c) => c.code).toSet();
    var saved = 0;
    for (final line in dtcText.split('\n')) {
      final code = line.trim().toUpperCase();
      if (code.isEmpty || known.contains(code)) continue;
      known.add(code);
      try {
        await api.post('/vehicles/${widget.vehicleId}/obd/codes',
            {'code': code, 'source': 'obd'});
        saved++;
      } catch (e) {
        debugPrint('ObdScreen._saveDeviceCodes($code) failed: '
            '${e.runtimeType}: $e');
      }
    }
    return saved;
  }

  /// First-time pairing: scan, let the user confirm WHICH dongle (AUT-966
  /// rule), remember its remoteId.
  Future<String?> _pairAdapter() async {
    setState(() => _adapterStatus = 'Looking for the adaptor…');
    try {
      final candidates = await DongleBle.scan();
      if (!mounted) return null;
      final choice = await showDialog<DonglePeripheral>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Confirm OBD adaptor'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Text('Pick your AutoBrain OBD2 ESP32 adaptor. Only '
                    'the device you pick will be used.'),
                const SizedBox(height: 8),
                for (final d in candidates)
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.settings_input_antenna),
                    title: Text(d.name),
                    subtitle: Text(d.deviceId),
                    onTap: () => Navigator.of(ctx).pop(d),
                  ),
              ],
            ),
          ),
          actions: [
            TextButton(
                onPressed: () => Navigator.of(ctx).pop(),
                child: const Text('Cancel')),
          ],
        ),
      );
      if (choice != null) await DongleSettings.saveBleId(choice.deviceId);
      return choice?.deviceId;
    } catch (e) {
      if (mounted) setState(() => _adapterStatus = _errorText(e));
      return null;
    }
  }

  Future<void> _clearDeviceCodes() async {
    final bleId = _bleId;
    if (bleId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Pair the adaptor first.')));
      return;
    }
    final messenger = ScaffoldMessenger.of(context);
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Clear codes on the car?'),
        content: const Text('The adaptor sends a mode-04 clear command: '
            'stored fault codes are erased and the check-engine light turns '
            'off. This needs the ignition on.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Clear codes')),
        ],
      ),
    );
    if (ok != true) return;
    setState(() {
      _syncing = true;
      _adapterStatus = 'Clearing codes on the car…';
    });
    try {
      await DongleBle.clearCodes(bleId);
      if (mounted) setState(() => _adapterStatus = 'Codes cleared on the car.');
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(_errorText(e))));
      if (mounted) setState(() => _adapterStatus = _errorText(e));
    } finally {
      if (mounted) setState(() => _syncing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('OBD')),
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
                      Card(
                        child: Padding(
                          padding: const EdgeInsets.symmetric(vertical: 4),
                          child: Column(
                            children: [
                              SwitchListTile(
                                secondary: Icon(
                                  Icons.bluetooth_connected,
                                  color: _bleId == null
                                      ? Colors.grey
                                      : Theme.of(context).colorScheme.primary,
                                ),
                                title: const Text('OBD adaptor'),
                                subtitle: Text(_adapterStatus ?? _adapterLabel),
                                value: _autoConnect,
                                onChanged: _enabled ? _setAutoConnect : null,
                              ),
                              Padding(
                                padding:
                                    const EdgeInsets.fromLTRB(16, 0, 16, 8),
                                child: Row(
                                  children: [
                                    FilledButton.tonalIcon(
                                      onPressed: _syncing
                                          ? null
                                          : () => _connectAndSync(manual: true),
                                      icon: const Icon(Icons.sync),
                                      label: Text(_bleId == null
                                          ? 'Pair & sync'
                                          : 'Connect & sync now'),
                                    ),
                                    if (_bleId != null) ...[
                                      const SizedBox(width: 8),
                                      FilledButton.tonalIcon(
                                        onPressed:
                                            _syncing ? null : _clearDeviceCodes,
                                        icon: const Icon(Icons.delete_outline),
                                        label: const Text('Clear codes'),
                                      ),
                                    ],
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                      if (_syncing) const LinearProgressIndicator(),
                      const SizedBox(height: 8),
                      const Card(
                        child: ListTile(
                          leading: Icon(Icons.route, color: Colors.green),
                          title: Text('Automatic trip recording'),
                          subtitle: Text(
                              'Trips start/stop automatically when the phone '
                              'connects to the car (car-kit / Android Auto) and '
                              'appear in the logbook marked "auto".'),
                        ),
                      ),
                      const SizedBox(height: 8),
                      Card(
                        child: ListTile(
                          leading: const Icon(Icons.settings_ethernet),
                          title: const Text('Vehicle VIN'),
                          subtitle: Text(
                            (_vin == null || _vin!.isEmpty)
                                ? 'Not set. Enter it manually.'
                                : _vin!,
                          ),
                          trailing: TextButton(
                              onPressed: _setVin, child: const Text('Set VIN')),
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
                                color:
                                    c.isResolved ? Colors.green : Colors.orange,
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
                          onPressed: () => _diagnoseCodes(
                              _codes.map((c) => c.code).toList()),
                          icon: const Icon(Icons.smart_toy),
                          label: const Text('Diagnose all codes with AI'),
                        ),
                      ],
                      if (AppConfig.isMobile && _enabled) ...[
                        const SizedBox(height: 24),
                        Text('Dongle WiFi upload',
                            style: Theme.of(context).textTheme.titleMedium),
                        const SizedBox(height: 8),
                        // AUT-1573: moved here from Settings — the dongle WiFi
                        // settings + provisioning, with its Sync now button.
                        Card(child: DongleWifiPanel()),
                      ],
                    ],
                  ),
                ),
    );
  }
}
