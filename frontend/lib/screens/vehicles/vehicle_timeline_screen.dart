import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/models.dart';
import '../../widgets/responsive.dart';

class VehicleTimelineScreen extends StatefulWidget {
  const VehicleTimelineScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<VehicleTimelineScreen> createState() => _VehicleTimelineScreenState();
}

class _VehicleTimelineScreenState extends State<VehicleTimelineScreen> {
  List<TimelineEvent> _events = const [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    setState(() => _loading = true);
    try {
      final data = await api.get('/vehicles/${widget.vehicleId}/timeline') as List;
      _events = data
          .map((e) => TimelineEvent.fromJson(e as Map<String, dynamic>))
          .toList();
    } catch (_) {}
    setState(() => _loading = false);
  }

  IconData _icon(String type) => switch (type) {
        'service' => Icons.build,
        'fuel' => Icons.local_gas_station,
        'mod' => Icons.tune,
        'diagnostic' => Icons.medical_services,
        _ => Icons.event,
      };

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Timeline')),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _events.isEmpty
                ? const Center(child: Text('No events yet'))
                : Center(
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 700),
                      child: ListView.builder(
                        padding: const EdgeInsets.all(16),
                        itemCount: _events.length,
                        itemBuilder: (context, i) {
                          final e = _events[i];
                          return Card(
                            child: ListTile(
                              leading: CircleAvatar(child: Icon(_icon(e.eventType))),
                              title: Text(e.title),
                              subtitle: Text(
                                '${DateFormat.yMMMd().format(DateTime.parse(e.occurredOn))}'
                                '${e.odometerKm != null ? ' · ${e.odometerKm} km' : ''}',
                              ),
                              trailing: e.amount != null
                                  ? Text(
                                      '${e.amount!.toStringAsFixed(0)}',
                                      style: Theme.of(context).textTheme.titleSmall,
                                    )
                                  : null,
                            ),
                          );
                        },
                      ),
                    ),
                  ),
                ),
      );
  }
}
