/// A subtle chip shown when the screen is rendering cached/stale data.
library;

import 'package:flutter/material.dart';

class StaleHint extends StatelessWidget {
  const StaleHint({super.key, required this.isStale, required this.isOffline});
  final bool isStale;
  final bool isOffline;

  @override
  Widget build(BuildContext context) {
    if (!isStale && !isOffline) return const SizedBox.shrink();
    final label = isOffline ? 'Offline — showing cached data' : 'Showing cached data';
    final icon = isOffline ? Icons.wifi_off_outlined : Icons.refresh_outlined;
    final color = isOffline
        ? Theme.of(context).colorScheme.error
        : Theme.of(context).colorScheme.primary;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      child: Chip(
        avatar: Icon(icon, size: 14, color: color),
        label: Text(
          label,
          style: TextStyle(color: color, fontSize: 11),
        ),
        visualDensity: VisualDensity.compact,
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      ),
    );
  }
}
