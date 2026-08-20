import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/models.dart';
import '../../services/obd/obd_trip_monitor.dart';
import '../diagnostics/add_diagnostic_screen.dart';

String _errorText(Object e) => e is ApiException ? e.message : '$e';

/// OBD fault-code library.
///
/// Generic ELM327/BT-SPP adapter support was removed (AUT-427) — the app only
/// supports the custom-built adapter, and trip start/stop comes from the
/// car-kit / Android Auto phone path (AUT-367). This screen keeps the
/// adapter-independent pieces: the saved fault-code library (manual add /
/// diagnose / clear) and the manual VIN entry.
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
  bool _loading = true;
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
      final settings = await api
          .get('/vehicles/${widget.vehicleId}/obd/settings') as Map<String, dynamic>;
      final codes = await api
              .get('/vehicles/${widget.vehicleId}/obd/codes') as List;
      final vehicle =
          await api.get('/vehicles/${widget.vehicleId}') as Map<String, dynamic>;
      setState(() {
        _enabled = (settings['enabled'] as bool?) ?? false;
        _codes = codes
            .map((e) => ObdCode.fromJson(e as Map<String, dynamic>))
            .toList();
        _vin = vehicle['vin'] as String?;
      });
      _monitor.arm(widget.vehicleId);
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
                        child: ListTile(
                          leading: const Icon(Icons.route, color: Colors.green),
                          title: const Text('Automatic trip recording'),
                          subtitle: const Text(
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
                              onPressed: _setVin,
                              child: const Text('Set VIN')),
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
