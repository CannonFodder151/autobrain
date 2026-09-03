/// Servo Spy — premium fuel-price explorer (AUT-1818, shell + Map/List).
///
/// Paid-tier feature: free accounts see the shared [PremiumGate] and never
/// any map/list data (gating requirement from AUT-1813). Paid accounts get a
/// theme-aware Map/List segmented view.
///
/// The map view (AUT-1820) renders live station markers with brand logos and
/// the current vehicle's fuel-type price, highlights the cheapest, and offers
/// a detail bottom sheet with all fuel prices + one-tap navigate.

library;

import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

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

/// Servo Spy map view — live station markers, cheapest highlight, detail sheet (AUT-1820).
class _ServoSpyMap extends StatefulWidget {
  const _ServoSpyMap();

  @override
  State<_ServoSpyMap> createState() => _ServoSpyMapState();
}

class _FuelPriceEntry {
  final String fuelType;
  final double? priceCents; // null = no price
  final double? costPerKm; // $/km (AUT-2201/2202, null without vehicle_id)
  final double? avgFillCost; // $ per fill (AUT-2201/2202)

  const _FuelPriceEntry({
    required this.fuelType,
    this.priceCents,
    this.costPerKm,
    this.avgFillCost,
  });
}

class _MapStation {
  final String id;
  final String? brand;
  final String? name;
  final String? address;
  final String? logoUrl;
  final double? lat;
  final double? lon;
  final double? distanceKm;
  final List<_FuelPriceEntry> prices;

  const _MapStation({
    required this.id,
    this.brand,
    this.name,
    this.address,
    this.logoUrl,
    this.lat,
    this.lon,
    this.distanceKm,
    required this.prices,
  });

  factory _MapStation.fromApi(Map<String, dynamic> m) {
    final rawPrices = (m['prices'] as List? ?? []) as List;
    return _MapStation(
      id: m['id'] as String? ?? '',
      brand: m['brand'] as String?,
      name: m['name'] as String? ?? 'Unknown',
      address: m['address'] as String?,
      logoUrl: m['logo'] as String?,
      lat: (m['lat'] as num?)?.toDouble(),
      lon: (m['lon'] as num?)?.toDouble(),
      distanceKm: (m['distance_km'] as num?)?.toDouble(),
      prices: rawPrices
          .map((p) => _FuelPriceEntry(
                fuelType: p['fuel_type'] as String? ?? '',
                priceCents: p['price'] != null ? (p['price'] as num).toDouble() : null,
                costPerKm: (p['cost_per_km'] as num?)?.toDouble(),
                avgFillCost: (p['avg_fill_cost'] as num?)?.toDouble(),
              ))
          .toList(),
    );
  }

  double? priceFor(String fuelType) {
    final p = prices.firstWhere(
      (p) => p.fuelType == fuelType,
      orElse: () => const _FuelPriceEntry(fuelType: ''),
    );
    return p.priceCents;
  }
}

class _ServoSpyMapState extends State<_ServoSpyMap> {
  bool _loading = true;
  String? _error;
  LatLng? _userLoc;
  bool _locationDenied = false;
  List<_MapStation> _stations = const [];
  List<String> _fuelTypes = List<String>.from(defaultFuelTypes);
  String? _selectedFuelType;
  String? _vehicleId;
  double _maxDistanceKm = 25;
  final MapController _mapController = MapController();
  LatLng? _mapCenter;
  bool _drifted = false;

  void _onMapEvent(MapEvent event) {
    if (event is MapEventMoveEnd) {
      final c = event.camera.center;
      _mapCenter = c;
      if (_userLoc != null) {
        final d = _userLoc!.latitude - c.latitude;
        final e = _userLoc!.longitude - c.longitude;
        _drifted = d * d + e * e > 0.0001;
      }
      if (mounted) setState(() {});
    }
  }

  void _recenter() {
    if (_userLoc == null) return;
    _mapController.move(_userLoc!, _mapController.camera.zoom);
    _drifted = false;
  }

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  Future<void> _bootstrap() async {
    setState(() => _loading = true);
    _error = null;

    final pos = await getCurrentPosition();
    if (pos != null) {
      _userLoc = LatLng(pos['latitude']!, pos['longitude']!);
      _locationDenied = false;
    } else {
      _locationDenied = true;
    }

    if (!mounted) return;

    if (_userLoc == null) {
      setState(() {
        _loading = false;
        _error = 'Enable location to find nearby stations.';
      });
      return;
    }

    try {
      final api = context.read<AuthState>().api;
      final vData = await api.get('/vehicles') as List;
      final vehicles = vData
          .map((e) => Vehicle.fromJson(e as Map<String, dynamic>))
          .toList();
      final current = Vehicle.resolveSelection(vehicles, null);
      _vehicleId = current?.id;
      _selectedFuelType = current?.fuelType;

      _fuelTypes = await fetchFuelTypes(api);
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
    if (_userLoc == null) return;
    setState(() => _loading = true);
    try {
      final api = context.read<AuthState>().api;
      final params = <String, String>{
        'lat': _userLoc!.latitude.toStringAsFixed(6),
        'lon': _userLoc!.longitude.toStringAsFixed(6),
        'radius_km': _maxDistanceKm.toInt().toString(),
        'limit': '50',
      };
      if (_vehicleId != null) params['vehicle_id'] = _vehicleId!;
      final qs = params.entries
          .map((e) => '${e.key}=${Uri.encodeComponent(e.value)}')
          .join('&');
      final data = await api.get('/fuel/stations?$qs') as List;
      final rows = data
          .map((e) => _MapStation.fromApi(e as Map<String, dynamic>))
          .toList();
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

  double? get _cheapestPrice {
    if (_selectedFuelType == null) return null;
    final prices = _stations
        .map((s) => s.priceFor(_selectedFuelType!))
        .where((p) => p != null)
        .cast<double>();
    if (prices.isEmpty) return null;
    return prices.reduce((a, b) => a < b ? a : b);
  }

  void _openStation(_MapStation s) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (_) => _StationSheet(station: s, userLoc: _userLoc),
    );
  }

  void _openFilter() {
    String fuel = _selectedFuelType ?? (_fuelTypes.isNotEmpty ? _fuelTypes.first : '91');
    double dist = _maxDistanceKm;
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
              Align(
                alignment: AlignmentDirectional.centerEnd,
                child: FilledButton(
                  onPressed: () {
                    Navigator.of(ctx).pop();
                    setState(() {
                      _selectedFuelType = fuel;
                      _maxDistanceKm = dist;
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

  static const _auCenter = LatLng(-25.2744, 133.7751);

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final scheme = Theme.of(context).colorScheme;
    final LatLng center = _userLoc ?? _auCenter;
    final markers = <Marker>[
      for (final s in _stations)
        if (s.lat != null && s.lon != null)
          Marker(
            point: LatLng(s.lat!, s.lon!),
            width: 72,
            height: 48,
            alignment: Alignment.topCenter,
            child: _StationMarker(
              station: s,
              selectedFuelType: _selectedFuelType,
              isCheapest: _cheapestPrice != null && s.priceFor(_selectedFuelType!) == _cheapestPrice,
              onTap: () => _openStation(s),
            ),
          ),
      if (_userLoc != null)
        Marker(
          point: _userLoc!,
          width: 22,
          height: 22,
          alignment: Alignment.center,
          child: Container(
            decoration: BoxDecoration(
              color: Colors.blue,
              shape: BoxShape.circle,
              border: Border.all(color: Colors.white, width: 3),
              boxShadow: const [
                BoxShadow(color: Colors.black38, blurRadius: 4),
              ],
            ),
          ),
        ),
    ];
    final showEmpty = !_loading &&
        _error == null &&
        _userLoc != null &&
        _stations.isEmpty;
    return Column(
      children: [
        if (_locationDenied)
          Container(
            width: double.infinity,
            color: Colors.amber.withValues(alpha: 0.15),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: const Text(
              'Location off — showing stations in the selected region. '
              'Enable location for nearby results.',
              style: TextStyle(fontSize: 12),
            ),
          ),
        Row(
          children: [
            if (_locationDenied)
              IconButton(
                tooltip: 'Enable location',
                icon: const Icon(Icons.location_disabled),
                onPressed: _bootstrap,
              ),
            const Spacer(),
            IconButton(
              tooltip: 'Refresh',
              icon: const Icon(Icons.refresh),
              onPressed: _bootstrap,
            ),
            IconButton(
              tooltip: 'Filters',
              icon: const Icon(Icons.filter_alt_outlined),
              onPressed: _openFilter,
            ),
          ],
        ),
        if (_selectedFuelType != null)
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
            child: Row(
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
          child: Stack(
            children: [
              Container(color: scheme.surfaceContainerHighest),
              FlutterMap(
                mapController: _mapController,
                options: MapOptions(
                  initialCenter: center,
                  initialZoom: _userLoc != null ? 12 : 11,
                  interactionOptions: InteractionOptions(
                    flags: InteractiveFlag.all & ~InteractiveFlag.rotate,
                  ),
                  onMapEvent: _onMapEvent,
                ),
                children: [
                  TileLayer(
                    urlTemplate: isDark
                        ? 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
                        : 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
                    subdomains: const ['a', 'b', 'c', 'd'],
                    userAgentPackageName: 'com.autobrain',
                  ),
                  MarkerLayer(markers: markers),
                ],
              ),
              if (_loading)
                const Positioned.fill(
                  child: ColoredBox(
                    color: Color(0x66000000),
                    child: Center(child: CircularProgressIndicator()),
                  ),
                ),
              if (showEmpty)
                Positioned.fill(
                  child: Center(
                    child: Container(
                      margin: const EdgeInsets.all(24),
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: scheme.surface.withValues(alpha: 0.95),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.local_gas_station_outlined,
                              size: 40, color: scheme.onSurfaceVariant),
                          const SizedBox(height: 8),
                          Text(
                            'No fuel stations within ${_maxDistanceKm.toInt()} km.',
                            style: Theme.of(context).textTheme.titleSmall,
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 4),
                          Text(
                            'Try increasing the distance in Filters.',
                            style: Theme.of(context)
                                .textTheme
                                .bodySmall
                                ?.copyWith(color: scheme.onSurfaceVariant),
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 12),
                          FilledButton.tonal(
                            onPressed: _openFilter,
                            child: const Text('Adjust filters'),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              if (_error != null && !_loading)
                Positioned(
                  left: 16,
                  right: 16,
                  top: 16,
                  child: Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: scheme.errorContainer,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      children: [
                        Icon(Icons.error_outline, color: scheme.onErrorContainer),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            'Prices unavailable: $_error',
                            style: TextStyle(color: scheme.onErrorContainer),
                          ),
                        ),
                        TextButton(onPressed: _bootstrap, child: const Text('Retry')),
                      ],
                    ),
                  ),
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
              if (_drifted && _userLoc != null)
                Positioned(
                  right: 16,
                  bottom: 28,
                  child: FloatingActionButton.small(
                    heroTag: 'servoSpyRecenter',
                    tooltip: 'Center on your location',
                    onPressed: _recenter,
                    child: const Icon(Icons.my_location),
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }
}

class _StationMarker extends StatelessWidget {
  const _StationMarker({
    required this.station,
    required this.selectedFuelType,
    required this.isCheapest,
    required this.onTap,
  });
  final _MapStation station;
  final String? selectedFuelType;
  final bool isCheapest;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final priceCents = selectedFuelType != null ? station.priceFor(selectedFuelType!) : null;
    final priceStr = priceCents != null && priceCents > 0
        ? '\$${(priceCents / 100).toStringAsFixed(1)}'
        : '—';
    final color = isCheapest
        ? const Color(0xFF57F287)
        : const Color(0xFF008C45);

    Widget? logo;
    if (station.logoUrl != null) {
      logo = ClipOval(
        child: Image.network(
          station.logoUrl!,
          width: 20,
          height: 20,
          fit: BoxFit.cover,
          errorBuilder: (_, __, ___) => Icon(Icons.local_gas_station, size: 16, color: Colors.white),
        ),
      );
    } else {
      logo = Icon(Icons.local_gas_station, size: 16, color: Colors.white);
    }

    return GestureDetector(
      onTap: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: color,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: Colors.white, width: 1.5),
              boxShadow: const [BoxShadow(color: Colors.black38, blurRadius: 3)],
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                logo,
                const SizedBox(width: 4),
                Text(
                  priceStr,
                  style: const TextStyle(
                    color: Colors.black,
                    fontWeight: FontWeight.w800,
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
          CustomPaint(
            size: const Size(12, 8),
            painter: _TrianglePainter(color),
          ),
        ],
      ),
    );
  }
}

class _TrianglePainter extends CustomPainter {
  const _TrianglePainter(this.color);
  final Color color;
  @override
  void paint(ui.Canvas canvas, ui.Size size) {
    final paint = ui.Paint()..color = color;
    canvas.drawPath(
      ui.Path()
        ..moveTo(0, 0)
        ..lineTo(size.width, 0)
        ..lineTo(size.width / 2, size.height)
        ..close(),
      paint,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter old) => false;
}

class _StationSheet extends StatelessWidget {
  const _StationSheet({required this.station, this.userLoc});
  final _MapStation station;
  final LatLng? userLoc;

  Future<void> _navigate(BuildContext context) async {
    if (station.lat == null || station.lon == null) return;
    final uri = Uri.https('www.google.com', '/maps/dir/', {
      if (userLoc != null) 'origin': '${userLoc!.latitude},${userLoc!.longitude}',
      'destination': '${station.lat},${station.lon}',
    });
    if (!await launchUrl(uri, mode: LaunchMode.externalApplication)) {
      await launchUrl(uri);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final sortedPrices = [...station.prices]..sort((a, b) =>
        (a.priceCents ?? double.infinity).compareTo(b.priceCents ?? double.infinity));
    return DraggableScrollableSheet(
      initialChildSize: 0.5,
      maxChildSize: 0.85,
      expand: false,
      builder: (_, scroll) => ListView(
        controller: scroll,
        padding: const EdgeInsets.all(16),
        children: [
          Text(station.name ?? 'Station',
              style: Theme.of(context).textTheme.titleLarge),
          if (station.address != null) ...[
            const SizedBox(height: 4),
            Text(station.address!,
                style: Theme.of(context).textTheme.bodyMedium),
          ],
          const SizedBox(height: 16),
          Text('Fuel prices', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          for (final p in sortedPrices)
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(Icons.local_gas_station, color: scheme.primary),
              title: Text(p.fuelType),
              subtitle: Text(
                p.costPerKm != null
                    ? '\$${p.costPerKm!.toStringAsFixed(3)}/km'
                        '${p.avgFillCost != null ? '  ·  fill \$${p.avgFillCost!.toStringAsFixed(2)}' : ''}'
                    : '—',
                style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 12),
              ),
              trailing: Text(
                p.priceCents == null
                    ? '—'
                    : '\$${(p.priceCents! / 100).toStringAsFixed(3)}',
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
            ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: () => _navigate(context),
              icon: const Icon(Icons.navigation),
              label: const Text('Navigate'),
            ),
          ),
        ],
      ),
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
