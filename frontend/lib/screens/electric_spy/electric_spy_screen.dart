/// Electric Spy — premium EV charging-station explorer (AUT-2435).
///
/// Fork of [ServoSpyScreen]: same Map/List segmented view + premium gate,
/// swapped domain (kWh vs cents/L, connector type vs fuel type, charging
/// icon vs fuel icon). Data comes from /api/ev/stations (Open Charge Map
/// via `app.services.ev_feeds`). No AI: deterministic, cache-first.

library;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../community_garage/widgets/premium_gate.dart';
import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/geoloc.dart';
import 'electric_spy_list_model.dart';

enum _EvView { map, list }

class ElectricSpyScreen extends StatefulWidget {
  const ElectricSpyScreen({super.key});

  @override
  State<ElectricSpyScreen> createState() => _ElectricSpyScreenState();
}

class _ElectricSpyScreenState extends State<ElectricSpyScreen> {
  _EvView _view = _EvView.map;

  static const String _cartoApiKey = String.fromEnvironment('CARTO_API_KEY');
  static const String _cartoKeyParam =
      _cartoApiKey.isEmpty ? '' : '?api_key=$_cartoApiKey';

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    return Scaffold(
      appBar: AppBar(title: const Text('Electric Spy')),
      body: auth.freeAccount
          ? const PremiumGate(
              lockedReason: 'Electric Spy is a premium member feature.',
            )
          : Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
                  child: SegmentedButton<_EvView>(
                    segments: const [
                      ButtonSegment(
                        value: _EvView.map,
                        label: Text('Map'),
                        icon: Icon(Icons.map_outlined),
                      ),
                      ButtonSegment(
                        value: _EvView.list,
                        label: Text('List'),
                        icon: Icon(Icons.list_alt_outlined),
                      ),
                    ],
                    selected: {_view},
                    onSelectionChanged: (s) => setState(() => _view = s.first),
                  ),
                ),
                Expanded(
                  child: _view == _EvView.map
                      ? const _EvMap()
                      : const _EvList(),
                ),
              ],
            ),
    );
  }
}

class _MapStation {
  final String id;
  final String? network;
  final String name;
  final String? address;
  final double? lat;
  final double? lon;
  final double? distanceKm;
  final List<_Connector> connectors;

  _MapStation({
    required this.id,
    required this.name,
    this.network,
    this.address,
    this.lat,
    this.lon,
    this.distanceKm,
    required this.connectors,
  });

  factory _MapStation.fromApi(Map<String, dynamic> m) {
    final raw = (m['connectors'] as List? ?? []) as List;
    return _MapStation(
      id: m['id'] as String? ?? '',
      network: m['network'] as String?,
      name: m['name'] as String? ?? 'Charging Station',
      address: m['address'] as String?,
      lat: (m['lat'] as num?)?.toDouble(),
      lon: (m['lon'] as num?)?.toDouble(),
      distanceKm: (m['distance_km'] as num?)?.toDouble(),
      connectors: raw
          .map((c) => _Connector(
                connectorType: (c['connector_type'] as String?) ?? '',
                maxPowerKw: (c['max_power_kw'] as num?)?.toDouble(),
                costPerKwh: (c['cost_per_kwh'] as num?)?.toDouble(),
                status: c['status'] as String?,
              ))
          .where((c) => c.connectorType.isNotEmpty)
          .toList(),
    );
  }

  double? costFor(String connectorType) {
    for (final c in connectors) {
      if (c.connectorType == connectorType) return c.costPerKwh;
    }
    return null;
  }

  double? cheapestCost() => cheapestCostPerKwh(connectors.map((c) => c.costPerKwh).toList());
}

class _Connector {
  final String connectorType;
  final double? maxPowerKw;
  final double? costPerKwh;
  final String? status;
  const _Connector({
    required this.connectorType,
    this.maxPowerKw,
    this.costPerKwh,
    this.status,
  });
}

class _EvMap extends StatefulWidget {
  const _EvMap();

  @override
  State<_EvMap> createState() => _EvMapState();
}

class _EvMapState extends State<_EvMap> {
  bool _loading = true;
  String? _error;
  LatLng? _userLoc;
  bool _locationDenied = false;
  List<_MapStation> _stations = const [];
  List<String> _connectorTypes = const [];
  String? _selectedConnectorType;
  double _maxDistanceKm = 25;
  final MapController _mapController = MapController();

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
        _error = 'Enable location to find nearby chargers.';
      });
      return;
    }

    try {
      final api = context.read<AuthState>().api;
      _connectorTypes =
          ((await api.get('/ev/types') as List?) ?? const [])
              .whereType<String>()
              .toList();
      if (_selectedConnectorType == null ||
          !_connectorTypes.contains(_selectedConnectorType)) {
        _selectedConnectorType =
            _connectorTypes.isNotEmpty ? _connectorTypes.first : null;
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
      if (_selectedConnectorType != null) {
        params['connector_type'] = _selectedConnectorType!;
      }
      final qs = params.entries
          .map((e) => '${e.key}=${Uri.encodeComponent(e.value)}')
          .join('&');
      final data = await api.get('/ev/stations?$qs') as List;
      final rows =
          data.map((e) => _MapStation.fromApi(e as Map<String, dynamic>)).toList();
      if (!mounted) return;
      setState(() {
        _stations = rows;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = 'Failed to load chargers (${e.statusCode}).');
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = 'Failed to load chargers.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  double? get _cheapest {
    if (_selectedConnectorType != null) {
      final prices = _stations
          .map((s) => s.costFor(_selectedConnectorType!))
          .whereType<double>()
          .where((c) => c > 0);
      if (prices.isEmpty) return null;
      return prices.reduce((a, b) => a < b ? a : b);
    }
    final prices = _stations
        .map((s) => s.cheapestCost())
        .whereType<double>()
        .where((c) => c > 0);
    if (prices.isEmpty) return null;
    return prices.reduce((a, b) => a < b ? a : b);
  }

  void _openStation(_MapStation s) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (_) => _StationSheet(station: s),
    );
  }

  void _openFilter() {
    String connector =
        _selectedConnectorType ?? (_connectorTypes.isNotEmpty ? _connectorTypes.first : 'CCS2');
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
                initialValue: _connectorTypes.contains(connector) ? connector : null,
                decoration: const InputDecoration(
                  labelText: 'Connector type',
                  border: OutlineInputBorder(),
                  isDense: true,
                ),
                items: _connectorTypes
                    .map((c) => DropdownMenuItem(value: c, child: Text(c)))
                    .toList(),
                onChanged: (v) => setSheet(() => connector = v ?? connector),
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
                      _selectedConnectorType = connector;
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

  void _recenter() {
    if (_userLoc == null) return;
    _mapController.move(_userLoc!, _mapController.camera.zoom);
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
            width: 84,
            height: 48,
            alignment: Alignment.topCenter,
            child: _StationMarker(
              station: s,
              selectedConnector: _selectedConnectorType,
              isCheapest: _isCheapest(s),
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
              boxShadow: const [BoxShadow(color: Colors.black38, blurRadius: 4)],
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
        if (_selectedConnectorType != null && _connectorTypes.isNotEmpty)
          SizedBox(
            height: 44,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 12),
              children: [
                for (final ct in _connectorTypes)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                      label: Text(ct),
                      selected: ct == _selectedConnectorType,
                      onSelected: (_) {
                        setState(() => _selectedConnectorType = ct);
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
                ),
                children: [
                  TileLayer(
                    urlTemplate: isDark
                        ? 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png${_cartoKeyParam}'
                        : 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png${_cartoKeyParam}',
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
                          Icon(Icons.ev_station_outlined,
                              size: 40, color: scheme.onSurfaceVariant),
                          const SizedBox(height: 8),
                          Text(
                            'No chargers within ${_maxDistanceKm.toInt()} km.',
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
                            'Chargers unavailable: $_error',
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
                    '© OpenStreetMap contributors © Open Charge Map © CARTO',
                    style: TextStyle(color: Colors.white, fontSize: 11),
                  ),
                ),
              ),
              if (_userLoc != null)
                Positioned(
                  right: 16,
                  bottom: 28,
                  child: FloatingActionButton.small(
                    heroTag: 'electricSpyRecenter',
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

  bool _isCheapest(_MapStation s) {
    final cheapest = _cheapest;
    if (cheapest == null) return false;
    final cost = _selectedConnectorType != null
        ? s.costFor(_selectedConnectorType!)
        : s.cheapestCost();
    return cost != null && cost == cheapest;
  }
}

class _StationMarker extends StatelessWidget {
  const _StationMarker({
    required this.station,
    required this.selectedConnector,
    required this.isCheapest,
    required this.onTap,
  });
  final _MapStation station;
  final String? selectedConnector;
  final bool isCheapest;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cost = selectedConnector != null
        ? station.costFor(selectedConnector!)
        : station.cheapestCost();
    final priceStr = cost != null && cost > 0
        ? '\$${cost.toStringAsFixed(2)}/kWh'
        : '—';
    final color = isCheapest
        ? const Color(0xFF57F287)
        : const Color(0xFF0EA5E9);
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
                const Icon(Icons.ev_station, size: 14, color: Colors.black),
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
        ],
      ),
    );
  }
}

class _StationSheet extends StatelessWidget {
  const _StationSheet({required this.station});
  final _MapStation station;

  Future<void> _navigate(BuildContext context) async {
    if (station.lat == null || station.lon == null) return;
    final uri = Uri.https('www.google.com', '/maps/dir/', {
      'destination': '${station.lat},${station.lon}',
    });
    if (!await launchUrl(uri, mode: LaunchMode.externalApplication)) {
      await launchUrl(uri);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final sorted = [...station.connectors]..sort((a, b) {
        final ac = a.costPerKwh;
        final bc = b.costPerKwh;
        if (ac == null && bc == null) return 0;
        if (ac == null) return 1;
        if (bc == null) return -1;
        return ac.compareTo(bc);
      });
    return DraggableScrollableSheet(
      initialChildSize: 0.5,
      maxChildSize: 0.85,
      expand: false,
      builder: (_, scroll) => ListView(
        controller: scroll,
        padding: const EdgeInsets.all(16),
        children: [
          Text(station.name,
              style: Theme.of(context).textTheme.titleLarge),
          if (station.network != null) ...[
            const SizedBox(height: 4),
            Text(station.network!,
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: scheme.onSurfaceVariant)),
          ],
          if (station.address != null) ...[
            const SizedBox(height: 4),
            Text(station.address!,
                style: Theme.of(context).textTheme.bodyMedium),
          ],
          const SizedBox(height: 16),
          Text('Connectors', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          for (final c in sorted)
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(Icons.ev_station, color: scheme.primary),
              title: Text(c.connectorType),
              subtitle: Text(
                [
                  if (c.maxPowerKw != null) '${c.maxPowerKw!.toStringAsFixed(0)} kW',
                  if (c.status != null && c.status!.isNotEmpty) c.status!,
                ].join(' · '),
                style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 12),
              ),
              trailing: Text(
                c.costPerKwh == null
                    ? '—'
                    : '\$${c.costPerKwh!.toStringAsFixed(2)}/kWh',
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

class _EvList extends StatefulWidget {
  const _EvList();

  @override
  State<_EvList> createState() => _EvListState();
}

class _EvListState extends State<_EvList> {
  bool _loading = true;
  String? _error;
  List<EvStationRow> _stations = const [];
  List<String> _connectorTypes = const [];
  String? _selectedConnectorType;
  double _maxDistanceKm = 25;
  EvSortMetric _sortMetric = EvSortMetric.price;
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
        _error = 'Enable location to find nearby chargers.';
      });
      return;
    }
    try {
      _connectorTypes = ((await _api.get('/ev/types') as List?) ?? const [])
          .whereType<String>()
          .toList();
      if (_selectedConnectorType == null ||
          !_connectorTypes.contains(_selectedConnectorType)) {
        _selectedConnectorType =
            _connectorTypes.isNotEmpty ? _connectorTypes.first : null;
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
      if (_selectedConnectorType != null) {
        params['connector_type'] = _selectedConnectorType!;
      }
      final qs = params.entries
          .map((e) => '${e.key}=${Uri.encodeComponent(e.value)}')
          .join('&');
      final data = await _api.get('/ev/stations?$qs') as List;
      final rows = data
          .map((e) => evStationRowFromApi(
                e as Map<String, dynamic>,
                selectedConnectorType: _selectedConnectorType,
              ))
          .toList();
      sortEvRows(rows, _sortMetric);
      if (!mounted) return;
      setState(() {
        _stations = rows;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _error = 'Failed to load chargers (${e.statusCode}).');
    } catch (_) {
      if (!mounted) return;
      setState(() => _error = 'Failed to load chargers.');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _openFilter() {
    String connector = _selectedConnectorType ??
        (_connectorTypes.isNotEmpty ? _connectorTypes.first : 'CCS2');
    double dist = _maxDistanceKm;
    EvSortMetric metric = _sortMetric;
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
                initialValue: _connectorTypes.contains(connector) ? connector : null,
                decoration: const InputDecoration(
                  labelText: 'Connector type',
                  border: OutlineInputBorder(),
                  isDense: true,
                ),
                items: _connectorTypes
                    .map((c) => DropdownMenuItem(value: c, child: Text(c)))
                    .toList(),
                onChanged: (v) => setSheet(() => connector = v ?? connector),
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
              SegmentedButton<EvSortMetric>(
                segments: const [
                  ButtonSegment(value: EvSortMetric.price, label: Text('Price')),
                  ButtonSegment(value: EvSortMetric.distance, label: Text('Distance')),
                  ButtonSegment(value: EvSortMetric.power, label: Text('Power')),
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
                      _selectedConnectorType = connector;
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
              Icon(Icons.ev_station_outlined, size: 18, color: scheme.onSurfaceVariant),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  _selectedConnectorType ?? 'All connectors',
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
        if (_connectorTypes.isNotEmpty)
          SizedBox(
            height: 44,
            child: ListView(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 12),
              children: [
                for (final ct in _connectorTypes)
                  Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: ChoiceChip(
                      label: Text(ct),
                      selected: ct == _selectedConnectorType,
                      onSelected: (_) {
                        setState(() => _selectedConnectorType = ct);
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
                            Icon(Icons.location_off_outlined,
                                size: 48, color: scheme.onSurfaceVariant),
                            const SizedBox(height: 12),
                            Text(_error!, textAlign: TextAlign.center),
                            const SizedBox(height: 16),
                            FilledButton.tonal(
                                onPressed: _bootstrap, child: const Text('Retry')),
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
                                Icon(Icons.ev_station_outlined,
                                    size: 56, color: scheme.onSurfaceVariant),
                                const SizedBox(height: 16),
                                Text('No chargers found.',
                                    style: Theme.of(context).textTheme.titleMedium),
                                const SizedBox(height: 8),
                                Text(
                                  'Try increasing the distance or changing the connector type.',
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
                            final priceLabel = s.costPerKwh != null
                                ? '\$${s.costPerKwh!.toStringAsFixed(2)}/kWh'
                                : '—';
                            final distLabel = s.distanceKm != null
                                ? '${s.distanceKm!.toStringAsFixed(1)} km'
                                : '';
                            final powerLabel = s.maxPowerKw != null
                                ? '${s.maxPowerKw!.toStringAsFixed(0)} kW'
                                : '';
                            final netLabel = s.network ?? s.connectorType ?? '';
                            return ListTile(
                              leading: CircleAvatar(
                                backgroundColor: scheme.surfaceContainerHighest,
                                child: Icon(Icons.ev_station, color: scheme.onSurfaceVariant),
                              ),
                              title: Text(s.name,
                                  maxLines: 1, overflow: TextOverflow.ellipsis),
                              subtitle: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Text(distLabel),
                                  Text(
                                    netLabel.isEmpty ? powerLabel : '$netLabel · $powerLabel',
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