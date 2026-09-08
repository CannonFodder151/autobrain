import 'package:flutter/material.dart';

import '../core/models.dart';

/// AUT-2415 — Inline rego status badge + expiry line. Renders nothing when
/// the vehicle has no rego data (forward-compatible with AUT-2414 nightly
/// job). [premium] controls whether the badge renders for free accounts
/// (gated behind premium per acceptance criteria).
class RegoStatusBadge extends StatelessWidget {
  const RegoStatusBadge({
    super.key,
    required this.vehicle,
    required this.premium,
    this.dense = false,
  });

  final Vehicle vehicle;
  final bool premium;
  final bool dense;

  static const _validTokens = {'valid', 'registered', 'current', 'active'};

  bool _isValid(String status) =>
      _validTokens.contains(status.toLowerCase().trim());

  @override
  Widget build(BuildContext context) {
    if (!vehicle.hasRegoData || !premium) return const SizedBox.shrink();

    final valid = _isValid(vehicle.regoStatus!);
    final expiry = vehicle.formattedRegoExpiry;
    final scheme = Theme.of(context).colorScheme;

    final bg = valid ? Colors.green.shade600 : Colors.red.shade600;
    final label = valid ? 'Rego valid' : 'Rego expired';
    final icon = valid ? Icons.verified : Icons.error_outline;

    if (dense) {
      return Wrap(
        spacing: 8,
        runSpacing: 6,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: bg,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(icon, size: 14, color: Colors.white),
                const SizedBox(width: 4),
                Text(label,
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 11,
                        fontWeight: FontWeight.w700)),
              ],
            ),
          ),
          if (expiry != null)
            Text('Expires: $expiry',
                style: TextStyle(
                    color: scheme.onSurfaceVariant,
                    fontSize: 12,
                    fontWeight: FontWeight.w500)),
        ],
      );
    }

    return Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Wrap(
        spacing: 8,
        runSpacing: 4,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
            decoration: BoxDecoration(
              color: bg,
              borderRadius: BorderRadius.circular(14),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(icon, size: 16, color: Colors.white),
                const SizedBox(width: 6),
                Text(label,
                    style: const TextStyle(
                        color: Colors.white,
                        fontSize: 12,
                        fontWeight: FontWeight.w700)),
              ],
            ),
          ),
          if (expiry != null)
            Text('Expires: $expiry',
                style: TextStyle(
                    color: scheme.onSurfaceVariant,
                    fontSize: 13,
                    fontWeight: FontWeight.w500)),
        ],
      ),
    );
  }
}