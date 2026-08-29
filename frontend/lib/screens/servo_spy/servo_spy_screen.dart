/// Servo Spy — premium fuel-price explorer (AUT-1818, shell + Map/List).
///
/// Paid-tier feature: free accounts see the shared [PremiumGate] and never
/// any map/list data (gating requirement from AUT-1813). Paid accounts get a
/// theme-aware Map/List segmented view.
///
/// ponytail: live station markers + list rows are intentionally absent — they
/// depend on the backend fuel-price API (AUT-1817), still blocked. Wire
/// `/api/fuel/stations` into [_ServoSpyMap]/[_ServoSpyList] once that ships.

library;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import '../../community_garage/widgets/premium_gate.dart';
import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/fuel_types.dart';
import '../../core/geoloc.dart';
import '../../core/models.dart';
import 'servo_spy_list_model.dart';

enum _ServoSpyView { map, list }

class ServoSpyScreen extends StatefulWidget {
  const ServoSpyScreen({super.key});

  @override
  State<ServoSpyScreen> createState() => _ServoSpyScreenState();
}

class _ServoSpyScreenState extends State<ServoSpyScreen> {
  _ServoSpyView _view = _ServoSpyView.map;

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    return Scaffold(
      appBar: AppBar(title: const Text('Servo Spy')),
      body: auth.freeAccount
          ? const PremiumGate(
              lockedReason: 'Servo Spy is a premium member feature.',
            )
          : Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
                  child: SegmentedButton<_ServoSpyView>(
                    segments: const [
                      ButtonSegment(
                        value: _ServoSpyView.map,
                        label: Text('Map'),
                        icon: Icon(Icons.map_outlined),
                      ),
                      ButtonSegment(
                        value: _ServoSpyView.list,
                        label: Text('List'),
                        icon: Icon(Icons.list_alt_outlined),
                      ),
                    ],
                    selected: {_view},
                    onSelectionChanged: (s) => setState(() => _view = s.first),
                  ),
                ),
                Expanded(
                  child: _view == _ServoSpyView.map
                      ? const _ServoSpyMap()
                      : const _ServoSpyList(),
                ),
              ],
            ),
    );
  }
}

/// Theme-aware basemap (CARTO light/dark) — no station markers yet (AUT-1817).
class _ServoSpyMap extends StatelessWidget {
  const _ServoSpyMap();

  static const _auCenter = LatLng(-25.2744, 133.7751);

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final tileUrl = dark
        ? 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png'
        : 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png';
    final scheme = Theme.of(context).colorScheme;
    return Stack(
      children: [
        FlutterMap(
          options: const MapOptions(
            initialCenter: _auCenter,
            initialZoom: 4,
            interactionOptions: InteractionOptions(
              flags: InteractiveFlag.all & ~InteractiveFlag.rotate,
            ),
          ),
          children: [
            TileLayer(
              urlTemplate: tileUrl,
              subdomains: ['a', 'b', 'c', 'd'],
              userAgentPackageName: 'com.autobrain',
            ),
          ],
        ),
        Positioned(
          left: 0,
          right: 0,
          bottom: 0,
          child: Container(
            color: scheme.scrim.withValues(alpha: 0.6),
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            child: const Text(
              '© OpenStreetMap contributors © CARTO',
              style: TextStyle(color: Colors.white, fontSize: 11),
            ),
          ),
        ),
        Center(
          child: Container(
            margin: const EdgeInsets.all(24),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: scheme.surface.withValues(alpha: 0.92),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(
              'Station markers appear once the live price feed is connected.',
              style: TextStyle(color: scheme.onSurfaceVariant),
              textAlign: TextAlign.center,
            ),
          ),
        ),
      ],
    );
  }
}

/// List view with sort + fuel-type/max-distance/sort-metric filters (AUT-1821).
class _ServoSpyList extends StatefulWidget {
  const _ServoSpyList();

  @override
  State<_ServoSpyList> createState() => _ServoSpyListState();
}

class _ServoSpyListState extends State<_ServoSpyList> {
  bool _loading = true;
  String? _error;
  List<ServoStationRow> _stations = const [];
  List<String> _fuelTypes = const [];
  String? _selectedFuelType;
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
      final qs = params.entries
          .map((e) => '${e.key}=${Uri.encodeComponent(e.value)}')
          .join('&');
      final data = await _api.get('/fuel/stations?$qs') as List;
      final rows = data.map((e) {
        final m = e as Map<String, dynamic>;
        final prices = (m['prices'] as List?) ?? [];
        final price = prices.isNotEmpty ? (prices[0]['price'] as num?)?.toDouble() : null;
        return ServoStationRow(
          name: m['name'] as String? ?? 'Unknown',
          brand: m['brand'] as String?,
          logoUrl: m['logo'] as String?,
          distanceKm: (m['distance_km'] as num?)?.toDouble(),
          priceCents: price,
          fuelType: prices.isNotEmpty ? prices[0]['fuel_type'] as String? : null,
        );
      }).toList();
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
                              subtitle: Text(distLabel),
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
