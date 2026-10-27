import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/models/servo_spy.dart';
import '../screens/servo_spy/servo_spy_station_history_screen.dart';

class ServoSpyStationMarker extends StatelessWidget {
  const ServoSpyStationMarker({
    super.key,
    required this.station,
    required this.selectedFuelType,
    required this.isCheapest,
    required this.onTap,
  });

  final MapStation station;
  final String? selectedFuelType;
  final bool isCheapest;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final priceCents = selectedFuelType != null ? station.priceFor(selectedFuelType!) : null;
    final priceStr = priceCents != null && priceCents > 0
        ? '\$${(priceCents / 100).toStringAsFixed(1)}'
        : '—';
    final color = isCheapest ? const Color(0xFF57F287) : const Color(0xFF008C45);

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

class ServoSpyStationSheet extends StatelessWidget {
  const ServoSpyStationSheet({super.key, required this.station, this.userLoc});

  final MapStation station;
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

  Future<void> _openHistory(BuildContext context) async {
    final stationId = station.id;
    if (stationId.isEmpty) return;
    final stationName = station.name ?? 'Station';
    Navigator.of(context, rootNavigator: true).pop();
    Navigator.of(context, rootNavigator: true).push(
      MaterialPageRoute(
        builder: (_) => ServoSpyStationHistoryScreen(
          stationId: stationId,
          stationName: stationName,
        ),
      ),
    );
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