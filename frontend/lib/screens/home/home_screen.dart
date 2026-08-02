import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/models.dart';
import '../../widgets/vehicle_selector.dart';
import '../analytics/analytics_screen.dart';
import '../diagnostics/diagnostics_screen.dart';
import '../fuel/fuel_screen.dart';
import '../mods/mods_screen.dart';
import '../parts/parts_screen.dart';
import '../receipts/receipts_screen.dart';
import '../services/service_list_screen.dart';
import '../valuation/valuation_screen.dart';
import '../vehicles/vehicle_list_screen.dart';
import '../vehicles/vehicle_timeline_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  List<Vehicle> _vehicles = const [];
  Vehicle? _selected;
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
      final data = await api.get('/vehicles') as List;
      final vehicles = data
          .map((e) => Vehicle.fromJson(e as Map<String, dynamic>))
          .toList();
      _vehicles = vehicles;
      _selected = _selected ?? _firstPrimary(vehicles);
    } catch (_) {}
    setState(() => _loading = false);
  }

  Vehicle? _firstPrimary(List<Vehicle> v) {
    for (final x in v) {
      if (x.isPrimary) return x;
    }
    return v.isEmpty ? null : v.first;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('AutoBrain'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: () => context.read<AuthState>().logout(),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  VehicleSelector(
                    vehicles: _vehicles,
                    selected: _selected,
                    onChanged: (v) => setState(() => _selected = v),
                    onManage: () async {
                      await Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => const VehicleListScreen(),
                        ),
                      );
                      _load();
                    },
                  ),
                  if (_selected == null)
                    const Padding(
                      padding: EdgeInsets.only(top: 32),
                      child: Text(
                        'Add a vehicle to get started.',
                        textAlign: TextAlign.center,
                      ),
                    ),
                  if (_selected != null) ...[
                    const SizedBox(height: 8),
                    _QuickStats(vehicle: _selected!),
                    const SizedBox(height: 16),
                    _FeatureGrid(vehicle: _selected!),
                  ],
                ],
              ),
      ),
    );
  }
}

class _QuickStats extends StatelessWidget {
  const _QuickStats({required this.vehicle});
  final Vehicle vehicle;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceAround,
          children: [
            _Stat(label: 'Odometer', value: '${vehicle.odometerKm ?? 0} km'),
            _Stat(label: 'Rego', value: vehicle.rego ?? '—'),
            _Stat(label: 'Condition', value: vehicle.condition),
          ],
        ),
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  const _Stat({required this.label, required this.value});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Column(
        children: [
          Text(value,
              style: Theme.of(context).textTheme.titleMedium),
          Text(label, style: Theme.of(context).textTheme.bodySmall),
        ],
      );
}

class _FeatureGrid extends StatelessWidget {
  const _FeatureGrid({required this.vehicle});
  final Vehicle vehicle;

  @override
  Widget build(BuildContext context) {
    final items = [
      _Feature('Timeline', Icons.timeline, VehicleTimelineScreen(vehicleId: vehicle.id)),
      _Feature('Services', Icons.build, ServiceListScreen(vehicleId: vehicle.id)),
      _Feature('Fuel', Icons.local_gas_station, FuelScreen(vehicleId: vehicle.id)),
      _Feature('Diagnostics', Icons.medical_services, DiagnosticsScreen(vehicleId: vehicle.id)),
      _Feature('Mods', Icons.tune, ModsScreen(vehicleId: vehicle.id)),
      _Feature('Receipts', Icons.receipt_long, ReceiptsScreen(vehicleId: vehicle.id)),
      _Feature('Parts', Icons.inventory_2, PartsScreen(vehicleId: vehicle.id)),
      _Feature('Valuation', Icons.sell, ValuationScreen(vehicleId: vehicle.id)),
      _Feature('Analytics', Icons.insights, AnalyticsScreen(vehicleId: vehicle.id)),
    ];
    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      childAspectRatio: 1.6,
      mainAxisSpacing: 12,
      crossAxisSpacing: 12,
      children: [
        for (final f in items)
          Card(
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => f.screen),
              ),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(f.icon, size: 28),
                  const SizedBox(height: 8),
                  Text(f.label),
                ],
              ),
            ),
          ),
      ],
    );
  }
}

class _Feature {
  const _Feature(this.label, this.icon, this.screen);
  final String label;
  final IconData icon;
  final Widget screen;
}
