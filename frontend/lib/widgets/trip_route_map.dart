/// Trip route rendered on a map (AUT-395, headline OBD2-port feature).
///
/// Deterministic polyline of the trip's GPS samples on an OpenStreetMap base.
/// Start/end points are marked; the view fits the whole route.
library;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

class TripRouteMap extends StatelessWidget {
  const TripRouteMap({super.key, required this.route});

  /// The cleaned route polyline (see `core/trip_route.dart`).
  final List<LatLng> route;

  @override
  Widget build(BuildContext context) {
    final bounds = LatLngBounds.fromPoints(route);
    final primary = Theme.of(context).colorScheme.primary;
    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: Stack(
        children: [
          FlutterMap(
            options: MapOptions(
              initialCameraFit: CameraFit.bounds(
                bounds: bounds,
                padding: const EdgeInsets.all(32),
              ),
              interactionOptions: const InteractionOptions(
                flags: InteractiveFlag.all & ~InteractiveFlag.rotate,
              ),
            ),
            children: [
              TileLayer(
                urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                userAgentPackageName: 'com.autobrain',
              ),
              PolylineLayer(
                polylines: [
                  Polyline(
                    points: route,
                    strokeWidth: 4,
                    color: primary,
                    borderColor: Colors.white,
                    borderStrokeWidth: 1.5,
                  ),
                ],
              ),
              MarkerLayer(
                markers: [
                  Marker(
                    point: route.first,
                    child: const _EndpointBadge(
                        icon: Icons.trip_origin, color: Color(0xFF22A55A)),
                  ),
                  Marker(
                    point: route.last,
                    child: const _EndpointBadge(
                        icon: Icons.flag, color: Color(0xFFC62828)),
                  ),
                ],
              ),
            ],
          ),
          Positioned(
            left: 0,
            right: 0,
            bottom: 0,
            child: Container(
              color: Colors.black.withOpacity(0.55),
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              child: const Text(
                '© OpenStreetMap contributors',
                style: TextStyle(color: Colors.white, fontSize: 11),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _EndpointBadge extends StatelessWidget {
  const _EndpointBadge({required this.icon, required this.color});

  final IconData icon;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        shape: BoxShape.circle,
        border: Border.all(color: color, width: 2),
      ),
      padding: const EdgeInsets.all(2),
      child: Icon(icon, color: color, size: 16),
    );
  }
}
