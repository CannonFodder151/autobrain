import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/auth_state.dart';
import '../../core/geoloc.dart';
import '../../core/models.dart';

const _fuelTypes = ['E10', 'U91', 'U95', 'U98', 'Diesel', 'LPG'];

// Cheapest-station highlight colour (green, per design-rule status tokens).
const _cheapestColor = Color(0xFF57F287);
// 7-Eleven brand green for the station markers.
const _brandColor = Color(0xFF008C45);

/// Servo Spy map: nearby 7-Eleven stations for the selected fuel type, with a
/// cheapest-station highlight and a detail sheet that can navigate to the store.
class ServoSpyMapScreen extends StatefulWidget {
  const ServoSpyMapScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<ServoSpyMapScreen> createState() => _ServoSpyMapScreenState();
}

class _ServoSpyMapScreenState extends State<ServoSpyMapScreen> {
  String _fuelType = 'U91';
  LatLng? _userLoc;
  List<FuelPriceQuote> _quotes = const [];
  bool _loading = true;
  bool _locationDenied = false;
  String? _error;
  double? _cheapestPrice;
  final MapController _mapController = MapController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final api = context.read<AuthState>().api;
    // Permission handling: try the device location; fall back to region mode
    // (still places markers) if the user denies or location is unavailable.
    LatLng? loc;
    try {
      final pos = await getCurrentPosition();
      if (pos != null) loc = LatLng(pos['latitude']!, pos['longitude']!);
    } catch (_) {}
    if (!mounted) return;
    setState(() {
      _userLoc = loc;
      _locationDenied = loc == null;
    });
    try {
      final query = <String, String>{
        'fuel_type': _fuelType,
        if (loc != null) ...{
          'lat': loc.latitude.toStringAsFixed(5),
          'lng': loc.longitude.toStringAsFixed(5),
          'max_results': '25',
        }
        else
          'region': 'All',
      };
      final data = await api.get(
        '/vehicles/${widget.vehicleId}/fuel/prices/7eleven',
        query: query,
      ) as Map<String, dynamic>;
      final quotes = (data['quotes'] as List? ?? [])
          .map((e) => FuelPriceQuote.fromJson(e as Map<String, dynamic>))
          .where((q) => q.lat != null && q.lng != null)
          .toList();
      final priced = quotes.where((q) => q.priceCpl > 0).toList();
      if (!mounted) return;
      setState(() {
        _quotes = quotes;
        _cheapestPrice = priced.isEmpty
            ? null
            : priced.map((q) => q.priceCpl).reduce((a, b) => a < b ? a : b);
        _error = null;
      });
      if (loc == null && quotes.isNotEmpty) {
        final c = quotes.first;
        _mapController.move(LatLng(c.lat!, c.lng!), 11);
      } else if (loc != null) {
        _mapController.move(loc, 12);
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _openStation(FuelPriceQuote q) async {
    if (q.lat == null || q.lng == null) return;
    final api = context.read<AuthState>().api;
    FuelStationDetail? detail;
    try {
      final data = await api.get(
        '/vehicles/${widget.vehicleId}/fuel/prices/7eleven/station',
        query: {
          'name': q.station,
          'lat': q.lat!.toStringAsFixed(5),
          'lng': q.lng!.toStringAsFixed(5),
        },
      ) as Map<String, dynamic>;
      detail = FuelStationDetail.fromJson(data);
    } catch (_) {
      // Fall back to the marker's single-fuel-type info if the detail lookup
      // fails (e.g. 503) so the user still gets a sheet + Navigate.
      detail = FuelStationDetail(
        station: q.station,
        suburb: q.suburb,
        state: q.state,
        postcode: q.postcode,
        address: '${q.suburb} ${q.state} ${q.postcode}'.trim(),
        lat: q.lat,
        lng: q.lng,
        prices: [StationFuelPrice(fuelType: q.fuelType, priceCpl: q.priceCpl)],
      );
    }
    if (!mounted) return;
    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (_) => _StationSheet(detail: detail!, userLoc: _userLoc),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final LatLng center;
    if (_userLoc != null) {
      center = _userLoc!;
    } else if (_quotes.where((q) => q.lat != null).isEmpty) {
      center = const LatLng(-33.8688, 151.2093);
    } else {
      center = LatLng(_quotes.first.lat!, _quotes.first.lng!);
    }
    final markers = <Marker>[
      for (final q in _quotes)
        if (q.lat != null && q.lng != null)
          Marker(
            point: LatLng(q.lat!, q.lng!),
            width: 72,
            height: 48,
            alignment: Alignment.topCenter,
            child: _StationMarker(
              quote: q,
              isCheapest: _cheapestPrice != null && q.priceCpl == _cheapestPrice,
              onTap: () => _openStation(q),
            ),
          ),
      if (_userLoc != null)
        Marker(
          point: _userLoc!,
          width: 22,
          height: 22,
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
    return Scaffold(
      appBar: AppBar(
        title: const Text('Servo Spy'),
        actions: [
          if (_locationDenied)
            IconButton(
              tooltip: 'Enable location',
              icon: const Icon(Icons.location_disabled),
              onPressed: _load,
            ),
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: _load,
          ),
        ],
      ),
      body: Column(
        children: [
          _FuelTypeBar(
            selected: _fuelType,
            onSelected: (ft) {
              setState(() => _fuelType = ft);
              _load();
            },
          ),
          if (_locationDenied)
            Container(
              width: double.infinity,
              color: Colors.amber.withValues(alpha: 0.15),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: const Text(
                'Location off — showing cheapest 7-Eleven stores by region. '
                'Enable location for nearby results.',
                style: TextStyle(fontSize: 12),
              ),
            ),
          Expanded(
            child: Stack(
              children: [
                FlutterMap(
                  mapController: _mapController,
                  options: MapOptions(
                    initialCenter: center,
                    initialZoom: _userLoc != null ? 12 : 11,
                    interactionOptions: const InteractionOptions(
                      flags: InteractiveFlag.all & ~InteractiveFlag.rotate,
                    ),
                  ),
                  children: [
                    TileLayer(
                      urlTemplate: isDark
                          ? 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
                          : 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                      subdomains: isDark ? const ['a', 'b', 'c', 'd'] : const [],
                      userAgentPackageName: 'com.autobrain',
                    ),
                    MarkerLayer(markers: markers),
                  ],
                ),
                if (_loading)
                  const Positioned.fill(
                    child: Center(child: CircularProgressIndicator()),
                  ),
                if (_error != null && !_loading)
                  Positioned(
                    left: 16,
                    right: 16,
                    bottom: 16,
                    child: Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.red.withValues(alpha: 0.9),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Text('Prices unavailable: $_error',
                          style: const TextStyle(color: Colors.white)),
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

class _FuelTypeBar extends StatelessWidget {
  const _FuelTypeBar({required this.selected, required this.onSelected});
  final String selected;
  final void Function(String) onSelected;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Row(
        children: [
          for (final ft in _fuelTypes)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: ChoiceChip(
                label: Text(ft),
                selected: ft == selected,
                onSelected: (_) => onSelected(ft),
              ),
            ),
        ],
      ),
    );
  }
}

class _StationMarker extends StatelessWidget {
  const _StationMarker({
    required this.quote,
    required this.isCheapest,
    required this.onTap,
  });
  final FuelPriceQuote quote;
  final bool isCheapest;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = isCheapest ? _cheapestColor : _brandColor;
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
            child: Text(
              '\$${(quote.priceCpl / 100).toStringAsFixed(1)}',
              style: const TextStyle(
                color: Colors.black,
                fontWeight: FontWeight.w800,
                fontSize: 12,
              ),
            ),
          ),
          // Pointer triangle pointing at the station.
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
  const _StationSheet({required this.detail, this.userLoc});
  final FuelStationDetail detail;
  final LatLng? userLoc;

  Future<void> _navigate() async {
    if (detail.lat == null || detail.lng == null) return;
    final uri = Uri.parse(
      'https://www.google.com/maps/dir/?api=1&destination=${detail.lat},${detail.lng}',
    );
    if (!await launchUrl(uri, mode: LaunchMode.externalApplication)) {
      await launchUrl(uri);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return DraggableScrollableSheet(
      initialChildSize: 0.5,
      maxChildSize: 0.85,
      expand: false,
      builder: (_, scroll) => ListView(
        controller: scroll,
        padding: const EdgeInsets.all(16),
        children: [
          Text(detail.station,
              style: Theme.of(context).textTheme.titleLarge),
          const SizedBox(height: 4),
          Text(detail.address,
              style: Theme.of(context).textTheme.bodyMedium),
          const SizedBox(height: 16),
          Text('Fuel prices', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          for (final p in detail.prices)
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: Icon(Icons.local_gas_station, color: scheme.primary),
              title: Text(p.fuelType),
              trailing: Text(
                p.priceCpl == null
                    ? '—'
                    : '\$${(p.priceCpl! / 100).toStringAsFixed(1)} /L',
                style: const TextStyle(fontWeight: FontWeight.w700),
              ),
            ),
          const SizedBox(height: 12),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: _navigate,
              icon: const Icon(Icons.navigation),
              label: const Text('Navigate'),
            ),
          ),
        ],
      ),
    );
  }
}
