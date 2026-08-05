import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/auth_state.dart';

/// Stripe subscription management: current plan + upgrade/downgrade/cancel.
class LicenseScreen extends StatefulWidget {
  const LicenseScreen({super.key});

  @override
  State<LicenseScreen> createState() => _LicenseScreenState();
}

class _LicenseScreenState extends State<LicenseScreen> {
  Map<String, dynamic>? _profile;
  bool _loading = true;
  bool _yearly = false;
  bool _busy = false;
  String? _error;

  String get _plan => ((_profile?['plan'] as String?) ?? 'free');
  String? get _subStatus => _profile?['subscription_status'] as String?;
  bool get _hasSub =>
      _subStatus == 'active' ||
      _subStatus == 'trialing' ||
      _subStatus == 'past_due';
  int get _maxVehicles => (_profile?['max_vehicles'] as int?) ?? 1;

  static const _statusLabels = {
    'active': 'Active',
    'trialing': 'Trial',
    'past_due': 'Past due',
    'canceled': 'Cancelled',
    'unpaid': 'Unpaid',
    'incomplete_expired': 'Expired',
  };

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final me = await api.get('/auth/me') as Map<String, dynamic>;
      setState(() => _profile = me);
    } catch (_) {
      setState(() => _error = 'Could not load your license status.');
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _checkout(String plan) async {
    final api = context.read<AuthState>().api;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final data = await api.post('/billing/checkout', {
        'plan': plan,
        'billing': _yearly ? 'yearly' : 'monthly',
      }) as Map<String, dynamic>;
      await _openUrl(data['url'] as String);
    } catch (e) {
      setState(() => _error = 'Could not start checkout: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _portal() async {
    final api = context.read<AuthState>().api;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final data =
          await api.post('/billing/portal') as Map<String, dynamic>;
      await _openUrl(data['url'] as String);
    } catch (e) {
      setState(() => _error = 'Could not open billing: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _openUrl(String url) async {
    final ok =
        await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
    if (!ok && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not open the link.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('License')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  _statusCard(context),
                  const SizedBox(height: 20),
                  Text('Plans',
                      style: Theme.of(context)
                          .textTheme
                          .titleMedium
                          ?.copyWith(fontWeight: FontWeight.w700)),
                  const SizedBox(height: 4),
                  Text('Upgrade any time — billed monthly or yearly by Stripe. '
                      'Cancel from your billing portal; your account stays '
                      'upgraded until the end of the period.',
                      style: Theme.of(context).textTheme.bodySmall),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      const Text('Billing period'),
                      const Spacer(),
                      SegmentedButton<bool>(
                        segments: const [
                          ButtonSegment(value: false, label: Text('Monthly')),
                          ButtonSegment(value: true, label: Text('Yearly')),
                        ],
                        selected: {_yearly},
                        onSelectionChanged: (s) =>
                            setState(() => _yearly = s.first),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  _planCard(
                    key: 'enthusiast',
                    name: 'Enthusiast',
                    price: _yearly ? r'$90' : r'$9',
                    period: _yearly ? '/year' : '/month',
                    vehicles: 1,
                    features: const [
                      '1 vehicle',
                      'All AI features included',
                      'Rego lookup',
                    ],
                  ),
                  const SizedBox(height: 16),
                  _planCard(
                    key: 'garage',
                    name: 'Garage',
                    price: _yearly ? r'$190' : r'$19',
                    period: _yearly ? '/year' : '/month',
                    vehicles: 5,
                    features: const [
                      '5 vehicles',
                      'All AI features included',
                      'Rego lookup',
                      'Priority support',
                    ],
                    popular: true,
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 16),
                    Text(_error!,
                        style: TextStyle(color: Colors.red.shade600)),
                  ],
                ],
              ),
            ),
    );
  }

  Widget _statusCard(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final IconData icon;
    final String title;
    final String subtitle;
    final Color color;
    if (_hasSub) {
      icon = Icons.verified_user;
      color = Colors.green;
      title = '${_plan == 'garage' ? 'Garage' : 'Enthusiast'} plan — '
          '${_statusLabels[_subStatus] ?? _subStatus}';
      subtitle = '$_maxVehicles vehicles, all AI features. '
          'Managed by Stripe.';
    } else {
      icon = Icons.info_outline;
      color = Colors.blue;
      title = 'Free plan';
      subtitle = '$_maxVehicles vehicle, no AI. '
          'Upgrade for rego lookup and more vehicles.';
    }
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: color),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(title,
                      style: const TextStyle(fontWeight: FontWeight.w700)),
                ),
                if (_hasSub)
                  IconButton(
                    icon: const Icon(Icons.manage_accounts_outlined),
                    tooltip: 'Manage subscription',
                    onPressed: _busy ? null : _portal,
                  ),
              ],
            ),
            const SizedBox(height: 4),
            Text(subtitle,
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: scheme.onSurfaceVariant)),
          ],
        ),
      ),
    );
  }

  Widget _planCard({
    required String key,
    required String name,
    required String price,
    required String period,
    required int vehicles,
    required List<String> features,
    bool popular = false,
  }) {
    final scheme = Theme.of(context).colorScheme;
    final isCurrent = _plan == key;
    return Card(
      shape: popular
          ? RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
              side: BorderSide(color: scheme.primary, width: 2),
            )
          : null,
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(name,
                      style: Theme.of(context)
                          .textTheme
                          .titleMedium
                          ?.copyWith(fontWeight: FontWeight.w800)),
                ),
                if (popular)
                  Chip(
                    label: const Text('Most popular'),
                    labelStyle: TextStyle(color: scheme.primary, fontSize: 12),
                    side: BorderSide(color: scheme.primary),
                    backgroundColor: scheme.primary.withValues(alpha: 0.1),
                  ),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              crossAxisAlignment: CrossAxisAlignment.baseline,
              textBaseline: TextBaseline.alphabetic,
              children: [
                Text(price,
                    style: TextStyle(
                        fontSize: 32,
                        fontWeight: FontWeight.w800,
                        color: scheme.primary)),
                const SizedBox(width: 4),
                Text(period,
                    style: TextStyle(color: scheme.onSurfaceVariant)),
              ],
            ),
            const SizedBox(height: 4),
            Text('$vehicles vehicle${vehicles == 1 ? '' : 's'}',
                style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 12),
            ...features.map(
              (f) => Padding(
                padding: const EdgeInsets.symmetric(vertical: 3),
                child: Row(
                  children: [
                    Icon(Icons.check_circle,
                        size: 18, color: scheme.primary),
                    const SizedBox(width: 8),
                    Expanded(child: Text(f)),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: _busy
                    ? null
                    : isCurrent
                        ? _portal
                        : () => _checkout(key),
                child: Text(isCurrent ? 'Manage subscription' : 'Upgrade to $name'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
