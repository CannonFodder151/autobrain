import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/download.dart';
import '../../core/models.dart';
import 'add_service_screen.dart';
import 'service_prediction_screen.dart';

class ServiceListScreen extends StatefulWidget {
  const ServiceListScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<ServiceListScreen> createState() => _ServiceListScreenState();
}

class _ServiceListScreenState extends State<ServiceListScreen> {
  List<ServiceRecord> _services = const [];
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
      final data =
          await api.get('/vehicles/${widget.vehicleId}/services') as List;
      _services = data
          .map((e) => ServiceRecord.fromJson(e as Map<String, dynamic>))
          .toList();
    } catch (_) {}
    setState(() => _loading = false);
  }

  Future<void> _export(String fmt) async {
    final api = context.read<AuthState>().api;
    try {
      final bytes = await api.export(
          '/vehicles/${widget.vehicleId}/services/export?fmt=$fmt');
      await downloadBytes('service-history.$fmt', bytes);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Export failed: $e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Service history'),
        actions: [
          PopupMenuButton<String>(
            onSelected: _export,
            itemBuilder: (_) => const [
              PopupMenuItem(value: 'csv', child: Text('Export CSV')),
              PopupMenuItem(value: 'pdf', child: Text('Export PDF')),
            ],
          ),
        ],
      ),
      floatingActionButton: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          FloatingActionButton.small(
            heroTag: 'predict',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(
                builder: (_) =>
                    ServicePredictionScreen(vehicleId: widget.vehicleId),
              ),
            ),
            child: const Icon(Icons.smart_toy),
            tooltip: 'AI prediction',
          ),
          const SizedBox(height: 12),
          FloatingActionButton.extended(
            heroTag: 'add',
            onPressed: () async {
              await Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (_) => AddServiceScreen(vehicleId: widget.vehicleId),
                ),
              );
              _load();
            },
            icon: const Icon(Icons.add),
            label: const Text('Log service'),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _services.isEmpty
                ? const Center(child: Text('No services logged'))
                : ListView.builder(
                    padding: const EdgeInsets.only(bottom: 96),
                    itemCount: _services.length,
                    itemBuilder: (context, i) {
                      final s = _services[i];
                      return Card(
                        child: ListTile(
                          title: Text(s.serviceType),
                          subtitle: Text(
                            '${s.serviceDate} · ${s.odometerKm} km'
                            '${s.workshop != null ? ' · ${s.workshop}' : ''}',
                          ),
                          trailing: Text('\$${s.cost.toStringAsFixed(0)}'),
                        ),
                      );
                    },
                  ),
      ),
    );
  }
}
