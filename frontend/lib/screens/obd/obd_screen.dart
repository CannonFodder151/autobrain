import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/models.dart';
import '../diagnostics/add_diagnostic_screen.dart';

/// OBD-II integration.
///
/// The live Bluetooth adapter features (auto-connect, live sensor streaming,
/// auto-populated VIN/codes) are an in-progress roadmap item — this screen is
/// the mobile/native integration seam. The codes library and "diagnose with
/// AI" already work against the backend.
class ObdScreen extends StatefulWidget {
  const ObdScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<ObdScreen> createState() => _ObdScreenState();
}

class _ObdScreenState extends State<ObdScreen> {
  List<ObdCode> _codes = const [];
  bool _enabled = false;
  bool _autoConnect = false;
  bool _loading = true;
  bool _vinMissing = false;

  @override
  void initState() {
    super.initState();
    _load();
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
    } catch (_) {}
    setState(() => _loading = false);
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
                    'Auto-populated from the OBD adapter once live OBD ships'),
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
                      Card(
                        color: Theme.of(context).colorScheme.surfaceContainerHighest,
                        child: const Padding(
                          padding: EdgeInsets.all(16),
                          child: Row(
                            children: [
                              Icon(Icons.construction, color: Colors.orange),
                              SizedBox(width: 12),
                              Expanded(
                                child: Text(
                                  'Live OBD logging (Bluetooth adapter, auto-connect, '
                                  'live data) is in progress — coming to the mobile app. '
                                  'The codes library and AI diagnosis below already work.',
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
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
                                'Auto-populate the VIN from the OBD adapter.'),
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
                              title: Text('${c.code}',
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