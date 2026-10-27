import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/fuel_types.dart';
import '../../core/geoloc.dart';
import '../../core/models.dart';
import '../../core/models/servo_spy.dart';
import '../../services/fuel_prices_api.dart';

class ServoSpyList extends StatefulWidget {
  const ServoSpyList({super.key});

  @override
  State<ServoSpyList> createState() => _ServoSpyListState();
}

class _ServoSpyListState extends State<ServoSpyList> {
  bool _loading = true;
  String? _error;
  List<ServoStationRow> _stations = const [];
  List<String> _fuelTypes = List<String>.from(defaultFuelTypes);
  String? _selectedFuelType;
  String? _vehicleId;
  double _maxDistanceKm = 25;
  ServoSortMetric _sortMetric = ServoSortMetric.price;
  late final ApiClient _api;
  Map<String, double>? _pos;

  @override
  void initState() {
    super.initState();
    _api = context.read<AuthState>().api;
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    setState(() => _loading = true);
    _error = null;

    _pos = await getCurrentPosition();
    if (_pos == null) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = 'Enable location to find nearby stations.';
      });
      return;
    }

    try {
      final data = await _api.get('/vehicles') as List;
      final vehicles = data
          .map((e) => Vehicle.fromJson(e as Map<String, dynamic>))
          .toList();
      final current = Vehicle.resolveSelection(vehicles, null);
      _vehicleId = current?.id;
      _selectedFuelType = current?.fuelType;

      _fuelTypes = await fetchFuelTypes(_api);
      if (_selectedFuelType == null || !_fuelTypes.contains(_selectedFuelType)) {
        _selectedFuelType = _fuelTypes.isNotEmpty ? _fuelTypes.first : null;
      }
      await _fetchStations();
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = 'Could not reach the server (${e.statusCode}).');
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = 'Could not load data. Check your connection.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _fetchStations() async {
    if (_pos == null) return;
    setState(() => _loading = true);
    try {
      final params = <String, String>{
        'lat': _pos!['latitude']!.toStringAsFixed(6),
        'lon': _pos!['longitude']!.toStringAsFixed(6),
        'radius_km': _maxDistanceKm.toInt().toString(),
      };
      if (_selectedFuelType != null) params['fuel_type'] = _selectedFuelType!;
      if (_vehicleId != null) params['vehicle_id'] = _vehicleId!;
      final qs = params.entries
          .map((e) => '${e.key}=${Uri.encodeComponent(e.value)}')
          .join('&');
      final data = await _api.get('/fuel/stations?$qs') as List;
      final selFuel = _selectedFuelType;
      final rows = data
          .map((e) => stationRowFromApi(
                e as Map<String, dynamic>,
                selectedFuelType: selFuel,
              ))
          .toList();
      sortStationRows(rows, _sortMetric);
      if (!mounted) return;
      setState(() {
        _stations = rows;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = 'Failed to load stations (${e.statusCode}).');
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = 'Failed to load stations.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _openFilter() {
    String fuel = _selectedFuelType ?? (_fuelTypes.isNotEmpty ? _fuelTypes.first : '91');
    double dist = _maxDistanceKm;
    ServoSortMetric metric = _sortMetric;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setSheet) => Padding(
          padding: const EdgeInsets.fromLTRB(16, 20, 16, 32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Filters', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 16),
              DropdownButtonFormField<String>(
                initialValue: fuel,
                decoration: const InputDecoration(
                  labelText: 'Fuel type',
                  border: OutlineInputBorder(),
                  isDense: true,
                ),
                items: _fuelTypes
                    .map((f) => DropdownMenuItem(value: f, child: Text(f)))
                    .toList(),
                onChanged: (v) => setSheet(() => fuel = v ?? fuel),
              ),
              const SizedBox(height: 20),
              Text('Max distance: ${dist.toInt()} km'),
              Slider(
                value: dist,
                min: 5,
                max: 200,
                divisions: 39,
                label: '${dist.toInt()} km',
                onChanged: (v) => setSheet(() => dist = v),
              ),
              const SizedBox(height: 16),
              Text('Sort by', style: Theme.of(context).textTheme.bodyMedium),
              const SizedBox(height: 8),
              SegmentedButton<ServoSortMetric>(
                segments: const [
                  ButtonSegment(value: ServoSortMetric.price, label: Text('Price')),
                  ButtonSegment(value: ServoSortMetric.distance, label: Text('Distance')),
                ],
                selected: {metric},
                onSelectionChanged: (s) => setSheet(() => metric = s.first),
              ),
              const SizedBox(height: 20),
              Align(
                alignment: AlignmentDirectional.centerEnd,
                child: FilledButton(
                  onPressed: () {
                    Navigator.of(ctx).pop();
                    setState(() {
                      _selectedFuelType = fuel;
                      _maxDistanceKm = dist;
                      _sortMetric = metric;
                    });
                    _fetchStations();
                  },
                  child: const Text('Apply'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Row(
            children: [
              Icon(Icons.local_gas_station_outlined, size: 18, color: scheme.onSurfaceVariant),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  _selectedFuelType ?? '—',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ),
              IconButton(
                icon: const Icon(Icons.filter_alt_outlined),
                tooltip: 'Filters',
                onPressed: _openFilter,
              ),
            ],
          ),
        ),
        if (_selectedFuelType != null && _fuelTypes.isNotEmpty)
          SizedBox(
            height: 44,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 12),
              children: [
                for (final ft in _fuelTypes)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                      label: Text(ft),
                      selected: ft == _selectedFuelType,
                      onSelected: (_) {
                        setState(() => _selectedFuelType = ft);
                        _fetchStations();
                      },
                    ),
                  ),
              ],
            ),
          ),
        Expanded(
          child: _loading
              ? const Center(child: CircularProgressIndicator())
              : _error != null
                  ? Center(
                      child: Padding(
                        padding: const EdgeInsets.all(24),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.location_off_outlined, size: 48, color: scheme.onSurfaceVariant),
                            const SizedBox(height: 12),
                            Text(_error!, textAlign: TextAlign.center),
                            const SizedBox(height: 16),
                            FilledButton.tonal(onPressed: _bootstrap, child: const Text('Retry')),
                          ],
                        ),
                      ),
                    )
                  : _stations.isEmpty
                      ? Center(
                          child: Padding(
                            padding: const EdgeInsets.all(32),
                            child: Column(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(Icons.local_gas_station_outlined, size: 56, color: scheme.onSurfaceVariant),
                                const SizedBox(height: 16),
                                Text('No stations found.', style: Theme.of(context).textTheme.titleMedium),
                                const SizedBox(height: 8),
                                Text(
                                  'Try increasing the distance or changing the fuel type.',
                                  textAlign: TextAlign.center,
                                  style: TextStyle(color: scheme.onSurfaceVariant),
                                ),
                              ],
                            ),
                          ),
                        )
                      : ListView.builder(
                          itemCount: _stations.length,
                          padding: const EdgeInsets.only(bottom: 24),
                          itemBuilder: (ctx, i) {
                            final s = _stations[i];
                            final priceLabel = s.priceCents != null
                                ? '\$${(s.priceCents! / 100).toStringAsFixed(3)}'
                                : '—';
                            final distLabel = s.distanceKm != null
                                ? '${s.distanceKm!.toStringAsFixed(1)} km'
                                : '';
                            final ckmLabel = s.costPerKm != null
                                ? '\$${s.costPerKm!.toStringAsFixed(3)}/km'
                                : '—';
                            final afcLabel = s.avgFillCost != null
                                ? 'fill \$${s.avgFillCost!.toStringAsFixed(2)}'
                                : '';
                            return ListTile(
                              leading: CircleAvatar(
                                backgroundColor: scheme.surfaceContainerHighest,
                                child: s.logoUrl != null
                                    ? ClipOval(
                                        child: Image.network(
                                          s.logoUrl!,
                                          width: 28,
                                          height: 28,
                                          fit: BoxFit.cover,
                                        ),
                                      )
                                    : Text(
                                        (s.brand ?? s.name).substring(0, 1).toUpperCase(),
                                        style: TextStyle(color: scheme.onSurfaceVariant),
                                      ),
                              ),
                              title: Text(s.name, maxLines: 1, overflow: TextOverflow.ellipsis),
                              subtitle: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Text(distLabel),
                                  Text(
                                    afcLabel.isEmpty
                                        ? ckmLabel
                                        : '$ckmLabel  ·  $afcLabel',
                                    style: TextStyle(
                                      color: scheme.onSurfaceVariant,
                                      fontSize: 12,
                                    ),
                                  ),
                                ],
                              ),
                              trailing: Text(
                                priceLabel,
                                style: Theme.of(context).textTheme.titleSmall?.copyWith(
                                      fontWeight: FontWeight.w600,
                                      color: scheme.primary,
                                    ),
                              ),
                            );
                          },
                        ),
        ),
      ],
    );
  }
}