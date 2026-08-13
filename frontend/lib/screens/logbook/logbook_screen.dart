import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/download.dart';
import '../../core/geoloc.dart';
import '../../core/models.dart';
import '../../core/trip_datetime.dart';
import '../../core/trip_route.dart';
import '../../widgets/trip_route_map.dart';

class LogbookScreen extends StatefulWidget {
  const LogbookScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<LogbookScreen> createState() => _LogbookScreenState();
}

class _LogbookScreenState extends State<LogbookScreen> {
  List<LogEntry> _entries = const [];
  bool _loading = true;
  int _fy = _currentFy();

  static int _currentFy() {
    final now = DateTime.now();
    return now.month >= 7 ? now.year + 1 : now.year;
  }

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    setState(() => _loading = true);
    try {
      final data = await api
              .get('/vehicles/${widget.vehicleId}/logbook?fy=$_fy') as List;
      _entries = data
          .map((e) => LogEntry.fromJson(e as Map<String, dynamic>))
          .toList();
    } catch (_) {}
    setState(() => _loading = false);
  }

  Future<void> _startTrip() async {
    await _tripDialog(null);
  }

  Future<void> _editTrip(LogEntry entry) async {
    await _tripDialog(entry);
  }

  Future<void> _deleteTrip(LogEntry entry) async {
    final api = context.read<AuthState>().api;
    try {
      await api.delete('/vehicles/${widget.vehicleId}/logbook/${entry.id}');
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  /// Fetches the full trip (incl. its GPS route) and shows it on a map.
  Future<void> _showRoute(LogEntry entry) async {
    final api = context.read<AuthState>().api;
    try {
      final detail = await api
              .get('/vehicles/${widget.vehicleId}/logbook/${entry.id}')
          as Map<String, dynamic>;
      final route = validRoute(LogEntry.fromJson(detail).gpsSamples);
      if (!mounted) return;
      if (route.length < 2) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('No GPS route recorded for this trip')));
        return;
      }
      await showDialog<void>(
        context: context,
        builder: (_) => Dialog.fullscreen(
          child: Scaffold(
            appBar: AppBar(
              title: Text(
                  'Trip route${entry.reason != null ? ' · ${entry.reason}' : ''}'),
            ),
            body: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Expanded(child: TripRouteMap(route: route)),
                  const SizedBox(height: 8),
                  Text(
                    '${route.length} GPS points · ${entry.startedAt?.substring(0, 16) ?? ''}',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
          ),
        ),
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Failed to load route: $e')));
      }
    }
  }

  Future<void> _export() async {
    final api = context.read<AuthState>().api;
    try {
      final bytes = await api.export(
          '/vehicles/${widget.vehicleId}/logbook/export?fy=$_fy');
      await downloadBytes('logbook-FY$_fy.csv', bytes);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Export failed: $e')));
      }
    }
  }

  Future<Map<String, double>?> _gps() async {
    try {
      return await getCurrentPosition();
    } catch (_) {
      return null;
    }
  }

  Future<void> _tripDialog(LogEntry? existing) async {
    final isEdit = existing != null;
    final isComplete = existing?.isComplete ?? false;
    final existingStart = existing?.startedAt ?? '';
    final dateCtrl = TextEditingController(
        text: existingStart.length >= 10 ? existingStart.substring(0, 10) : '');
    final timeCtrl = TextEditingController();
    final odoStart = TextEditingController(
        text: existing?.startOdometerKm?.toString() ?? '');
    final odoEnd = TextEditingController(
        text: existing?.endOdometerKm?.toString() ?? '');
    final locStart = TextEditingController(
        text: existing?.startLocation ?? '');
    final locEnd = TextEditingController(text: existing?.endLocation ?? '');
    final reasonCtrl = TextEditingController(text: existing?.reason ?? '');
    var purpose = existing?.purpose ?? 'private';

    if (existingStart.length >= 16) {
      timeCtrl.text = existingStart.substring(11, 16);
    }
    if (!isEdit) {
      final now = DateTime.now();
      dateCtrl.text = now.toString().substring(0, 10);
      timeCtrl.text = '${now.hour.toString().padLeft(2, '0')}:'
          '${now.minute.toString().padLeft(2, '0')}';
    }

    final formKey = GlobalKey<FormState>();
    var lat = existing?.startLat;
    var lng = existing?.startLng;
    final entryId = existing?.id;

    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setModal) => AlertDialog(
          title: Text(isComplete
              ? 'Trip details'
              : isEdit
                  ? 'Edit trip'
                  : 'Start trip'),
          content: SingleChildScrollView(
            child: Form(
              key: formKey,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: TextFormField(
                          controller: dateCtrl,
                          decoration: const InputDecoration(
                            labelText: 'Date',
                            hintText: '11/08/2026',
                          ),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: TextFormField(
                          controller: timeCtrl,
                          decoration: const InputDecoration(
                            labelText: 'Time',
                            hintText: '3:30 pm',
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  TextFormField(
                    controller: odoStart,
                    decoration: const InputDecoration(
                      labelText: 'Start odometer (km)',
                    ),
                    keyboardType: TextInputType.number,
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: TextFormField(
                          controller: locStart,
                          decoration:
                              const InputDecoration(labelText: 'Start location'),
                        ),
                      ),
                      IconButton(
                        tooltip: 'Use GPS',
                        icon: const Icon(Icons.my_location),
                        onPressed: () async {
                          final pos = await _gps();
                          if (pos == null) {
                            ScaffoldMessenger.of(ctx).showSnackBar(const SnackBar(
                                content: Text('GPS unavailable')));
                            return;
                          }
                          setModal(() {
                            lat = pos['latitude'];
                            lng = pos['longitude'];
                            if (locStart.text.isEmpty) {
                              locStart.text =
                                  '${lat!.toStringAsFixed(5)}, ${lng!.toStringAsFixed(5)}';
                            }
                          });
                        },
                      ),
                    ],
                  ),
                  if (isEdit) ...[
                    const SizedBox(height: 8),
                    TextFormField(
                      controller: odoEnd,
                      decoration: const InputDecoration(
                        labelText: 'End odometer (km)',
                      ),
                      keyboardType: TextInputType.number,
                    ),
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Expanded(
                          child: TextFormField(
                            controller: locEnd,
                            decoration: const InputDecoration(
                                labelText: 'End location'),
                          ),
                        ),
                        IconButton(
                          tooltip: 'Use GPS',
                          icon: const Icon(Icons.my_location),
                          onPressed: () async {
                            final pos = await _gps();
                            if (pos == null) return;
                            setModal(() {
                              if (locEnd.text.isEmpty) {
                                locEnd.text =
                                    '${pos['latitude']!.toStringAsFixed(5)}, '
                                    '${pos['longitude']!.toStringAsFixed(5)}';
                              }
                            });
                          },
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                  ] else ...[
                    const SizedBox(height: 8),
                  ],
                  const SizedBox(height: 8),
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Work trip'),
                    value: purpose == 'work',
                    onChanged: (v) =>
                        setModal(() => purpose = (v ?? false) ? 'work' : 'private'),
                  ),
                  TextFormField(
                    controller: reasonCtrl,
                    decoration: const InputDecoration(
                        labelText: 'Reason (e.g. client visit)'),
                  ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () async {
                if (!formKey.currentState!.validate()) return;
                final startedAt =
                    parseLogbookDateTime(dateCtrl.text, timeCtrl.text);
                if (startedAt == null) {
                  ScaffoldMessenger.of(ctx).showSnackBar(const SnackBar(
                      content: Text('Invalid start date/time')));
                  return;
                }
                final api = context.read<AuthState>().api;
                try {
                  final startOdo = int.tryParse(odoStart.text.trim());
                  final endOdo = isEdit ? int.tryParse(odoEnd.text.trim()) : null;
                  final body = <String, dynamic>{
                    'started_at': startedAt.toUtc().toIso8601String(),
                    'purpose': purpose,
                    if (startOdo != null) 'start_odometer_km': startOdo,
                    if (locStart.text.trim().isNotEmpty)
                      'start_location': locStart.text.trim(),
                    if (lat != null) 'start_lat': lat,
                    if (lng != null) 'start_lng': lng,
                    if (reasonCtrl.text.trim().isNotEmpty)
                      'reason': reasonCtrl.text.trim(),
                    if (isEdit && endOdo != null) 'end_odometer_km': endOdo,
                    if (isEdit && locEnd.text.trim().isNotEmpty)
                      'end_location': locEnd.text.trim(),
                    if (isEdit) 'status': 'completed',
                  };
                  if (isEdit) {
                    await api.patch(
                        '/vehicles/${widget.vehicleId}/logbook/$entryId',
                        body);
                  } else {
                    await api.post(
                        '/vehicles/${widget.vehicleId}/logbook', body);
                  }
                  if (ctx.mounted) Navigator.pop(ctx);
                  _load();
                } catch (e) {
                  if (ctx.mounted) {
                    ScaffoldMessenger.of(ctx)
                        .showSnackBar(SnackBar(content: Text('$e')));
                  }
                }
              },
              child: Text(isEdit ? 'Save' : 'Start trip'),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final work = _entries.where((e) => e.purpose == 'work').toList();
    final totalKm =
        _entries.fold<double>(0, (a, b) => a + (b.distanceKm ?? 0));
    final workKm = work.fold<double>(0, (a, b) => a + (b.distanceKm ?? 0));
    return Scaffold(
      appBar: AppBar(
        title: const Text('Logbook (ATO)'),
        actions: [
          IconButton(
            tooltip: 'Export financial year',
            icon: const Icon(Icons.download_outlined),
            onPressed: _export,
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _startTrip,
        icon: const Icon(Icons.add),
        label: const Text('Start trip'),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 96),
                children: [
                  DropdownButtonFormField<int>(
              value: _fy,
              decoration: const InputDecoration(labelText: 'Financial year'),
              items: [
                for (var fy = _currentFy() + 1; fy >= _currentFy() - 2; fy--)
                  DropdownMenuItem(
                      value: fy,
                      child: Text('FY${fy - 1}-${fy.toString().substring(2)}')),
              ],
              onChanged: (v) {
                setState(() => _fy = v ?? _currentFy());
                _load();
              },
            ),
            const SizedBox(height: 12),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceAround,
                  children: [
                    _v(context, 'Trips', '${_entries.length}'),
                    _v(context, 'Total km', totalKm.toStringAsFixed(0)),
                    _v(context, 'Work km', workKm.toStringAsFixed(0)),
                    _v(
                        context,
                        'Work %',
                        totalKm == 0
                            ? '—'
                            : '${(workKm / totalKm * 100).round()}%'),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            for (final e in _entries)
              Card(
                child: ListTile(
                  leading: Icon(
                    e.purpose == 'work' ? Icons.work : Icons.directions_car,
                    color: e.isComplete ? Colors.green : Colors.orange,
                  ),
                  title: Text(
                    '${e.startedAt?.substring(0, 16) ?? ''}'
                    '${e.reason != null ? ' · ${e.reason}' : ''}',
                  ),
                  subtitle: Text(
                    '${e.purpose}'
                    '${e.isAutoLogged ? ' · ${e.autoSourceLabel}' : ''}'
                    '${e.startOdometerKm != null ? ' · ${e.startOdometerKm} km' : ''}'
                    '${e.endOdometerKm != null ? ' → ${e.endOdometerKm} km' : ''}'
                    '${e.distanceKm != null ? ' · ${e.distanceKm!.toStringAsFixed(0)} km' : ''}'
                    '${e.isComplete ? '' : ' · IN PROGRESS'}',
                  ),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      IconButton(
                        tooltip: 'View route',
                        icon: const Icon(Icons.route),
                        onPressed: () => _showRoute(e),
                      ),
                      PopupMenuButton<String>(
                        onSelected: (v) {
                          if (v == 'edit') _editTrip(e);
                          if (v == 'delete') _deleteTrip(e);
                        },
                        itemBuilder: (_) => const [
                          PopupMenuItem(value: 'edit', child: Text('Edit / complete')),
                          PopupMenuItem(value: 'delete', child: Text('Delete')),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            if (_entries.isEmpty)
              const Padding(
                padding: EdgeInsets.only(top: 40),
                child: Center(
                  child: Text(
                    'Start a trip to record it in the logbook.\n'
                    'Mark trips as Work for your ATO logbook claim.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: Colors.grey),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _v(BuildContext context, String label, String value) => Column(
        children: [
          Text(value, style: Theme.of(context).textTheme.titleMedium),
          Text(label, style: Theme.of(context).textTheme.bodySmall),
        ],
      );
}
