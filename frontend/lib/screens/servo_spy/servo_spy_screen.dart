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
import '../../core/auth_state.dart';

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

/// Placeholder list — rows arrive with the fuel-price API (AUT-1817).
class _ServoSpyList extends StatelessWidget {
  const _ServoSpyList();

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.local_gas_station_outlined, size: 56, color: scheme.onSurfaceVariant),
            const SizedBox(height: 16),
            Text('No fuel stations loaded yet.',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(
              'Nearby servos and prices will list here once the price feed is live.',
              textAlign: TextAlign.center,
              style: TextStyle(color: scheme.onSurfaceVariant),
            ),
          ],
        ),
      ),
    );
  }
}
