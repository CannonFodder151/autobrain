import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/download.dart';
import '../../core/models.dart';
import 'service_form_screen.dart';
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
      final data = await api.get('/vehicles/${widget.vehicleId}/services') as List;
      _services = data
          .map((e) => ServiceRecord.fromJson(e as Map<String, dynamic>))
          .toList();
    } catch (_) {}
    setState(() => _loading = false);
  }

  Future<void> _markCompleted(ServiceRecord s) async {
    final api = context.read<AuthState>().api;
    try {
      await api.patch('/vehicles/${widget.vehicleId}/services/${s.id}', {
        'status': 'completed',
      });
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    }
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

  Future<void> _openForm([ServiceRecord? service]) async {
    final saved = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) =>
            ServiceFormScreen(vehicleId: widget.vehicleId, service: service),
      ),
    );
    if (saved == true) _load();
  }

  @override
  Widget build(BuildContext context) {
    final upcoming = _services.where((s) => s.isScheduled).toList();
    final history = _services.where((s) => !s.isScheduled).toList();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Services'),
        actions: [
          PopupMenuButton<String>(
            onSelected: _export,
            itemBuilder: (_) => const [
              PopupMenuItem(value: 'csv', child: Text('Export CSV')),
              PopupMenuItem(value: 'pdf', child: Text('Export PDF')),
              PopupMenuItem(
                  value: 'zip', child: Text('Export CSV + images (ZIP)')),
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
            onPressed: () => _openForm(),
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
                : ListView(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 96),
                    children: [
                      if (upcoming.isNotEmpty) ...[
                        _SectionHeader(
                          title: 'Upcoming',
                          count: upcoming.length,
                          icon: Icons.schedule,
                        ),
                        for (final s in upcoming) _ServiceCard(service: s, onEdit: _openForm, onComplete: _markCompleted),
                        const SizedBox(height: 16),
                      ],
                      _SectionHeader(
                        title: 'History',
                        count: history.length,
                        icon: Icons.history,
                      ),
                      for (final s in history) _ServiceCard(service: s, onEdit: _openForm, onComplete: _markCompleted),
                    ],
                  ),
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.title, required this.count, required this.icon});
  final String title;
  final int count;
  final IconData icon;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Row(
          children: [
            Icon(icon, size: 20, color: Theme.of(context).colorScheme.primary),
            const SizedBox(width: 8),
            Text(
              '$title ($count)',
              style: Theme.of(context)
                  .textTheme
                  .titleMedium
                  ?.copyWith(fontWeight: FontWeight.w700),
            ),
          ],
        ),
      );
}

class _ServiceCard extends StatelessWidget {
  const _ServiceCard({
    required this.service,
    required this.onEdit,
    required this.onComplete,
  });
  final ServiceRecord service;
  final void Function(ServiceRecord?) onEdit;
  final void Function(ServiceRecord) onComplete;

  @override
  Widget build(BuildContext context) {
    final items = service.items;
    final steps = service.steps;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: ExpansionTile(
        leading: service.isScheduled
            ? const Icon(Icons.schedule, color: Colors.amber)
            : const Icon(Icons.check_circle, color: Colors.green),
        title: Text(service.serviceType),
        subtitle: Text(
          '${service.serviceDate} · ${service.odometerKm} km'
          '${service.workshop != null ? ' · ${service.workshop}' : ''}',
        ),
        trailing: Text(
          service.cost > 0 ? '\$${service.cost.toStringAsFixed(0)}' : '',
          style: Theme.of(context).textTheme.titleSmall,
        ),
        children: [
          if (items.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Items',
                      style: Theme.of(context).textTheme.labelLarge),
                  for (final it in items)
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Row(
                        children: [
                          Icon(
                            it.kind == 'labour' ? Icons.handyman : Icons.settings,
                            size: 16,
                            color: Colors.grey,
                          ),
                          const SizedBox(width: 8),
                          Expanded(child: Text(it.name)),
                          if (it.partNo != null)
                            Text(it.partNo!,
                                style: Theme.of(context).textTheme.bodySmall),
                          const SizedBox(width: 8),
                          Text(
                            it.quantity > 1 ? 'x${it.quantity} ' : '',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                          Text('\$${it.total.toStringAsFixed(2)}'),
                        ],
                      ),
                    ),
                ],
              ),
            ),
          if (steps.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Steps', style: Theme.of(context).textTheme.labelLarge),
                  for (var i = 0; i < steps.length; i++)
                    Padding(
                      padding: const EdgeInsets.only(top: 2),
                      child: Text('${i + 1}. ${steps[i]}'),
                    ),
                ],
              ),
            ),
          if (service.description != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
              child: Text(service.description!,
                  style: Theme.of(context).textTheme.bodySmall),
            ),
          if (service.notes != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
              child: Text(service.notes!,
                  style: Theme.of(context).textTheme.bodySmall),
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(8, 0, 8, 8),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                if (service.isScheduled)
                  TextButton.icon(
                    onPressed: () => onComplete(service),
                    icon: const Icon(Icons.check_circle_outline, size: 18),
                    label: const Text('Mark completed'),
                  ),
                TextButton.icon(
                  onPressed: () => onEdit(service),
                  icon: const Icon(Icons.edit_outlined, size: 18),
                  label: const Text('Edit'),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
