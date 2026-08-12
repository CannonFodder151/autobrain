/// Community Garage shared UI widgets.
library;

import 'package:flutter/material.dart';

import '../../screens/settings/license_screen.dart';

/// Full-screen locked state for free accounts (rev 4). Shown instead of the
/// feed — never partial data. CTA routes to the Stripe license screen.
class PremiumGate extends StatelessWidget {
  const PremiumGate({super.key, this.lockedReason = 'Community Garage is a premium member feature.'});

  final String lockedReason;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.workspace_premium, size: 64, color: scheme.primary),
            const SizedBox(height: 16),
            Text('Premium feature',
                style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800)),
            const SizedBox(height: 8),
            Text(lockedReason,
                textAlign: TextAlign.center,
                style: TextStyle(color: scheme.onSurfaceVariant)),
            const SizedBox(height: 24),
            FilledButton.icon(
              icon: const Icon(Icons.arrow_upward),
              label: const Text('Upgrade to premium'),
              onPressed: () => Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const LicenseScreen()),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Locked overlay for individual actions on free accounts (detail screen).
class LockedAction extends StatelessWidget {
  const LockedAction({super.key, required this.icon, required this.label});
  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Tooltip(
      message: 'Available on premium',
      child: Opacity(
        opacity: 0.45,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 20, color: scheme.onSurfaceVariant),
            const SizedBox(width: 4),
            Text(label, style: Theme.of(context).textTheme.labelMedium),
          ],
        ),
      ),
    );
  }
}
