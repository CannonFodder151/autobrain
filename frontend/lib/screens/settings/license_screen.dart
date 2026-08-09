import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/auth_state.dart';

/// Stripe subscription management: current plan + upgrade/downgrade/cancel.
/// Prices come from GET /billing/pricing (with the early-adopter sale); the
/// values below are a fallback for hosts that do not expose /billing/pricing.
class LicenseScreen extends StatefulWidget {
  const LicenseScreen({super.key});

  @override
  State<LicenseScreen> createState() => _LicenseScreenState();
}

class _LicenseScreenState extends State<LicenseScreen> {
  static const _fallbackPlans = [
    {'key': 'enthusiast', 'name': 'Enthusiast', 'monthly': 900, 'yearly': 8400},
    {'key': 'garage', 'name': 'Garage', 'monthly': 1900, 'yearly': 16800},
  ];

  final _promoController = TextEditingController();

  Map<String, dynamic>? _profile;
  List<Map<String, dynamic>> _plans = _fallbackPlans;
  Map<String, dynamic> _sale = const {};
  bool _saleActive = false;
  bool _loading = true;
  bool _yearly = false;
  bool _busy = false;
  String? _error;

  String? get _subStatus => _profile?['subscription_status'] as String?;
  bool get _hasSub =>
      _subStatus == 'active' ||
      _subStatus == 'trialing' ||
      _subStatus == 'past_due';
  int get _maxVehicles => (_profile?['max_vehicles'] as int?) ?? 1;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _promoController.dispose();
    super.dispose();
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
    }
    // Pricing is public; ignore failures so a host without it still renders.
    try {
      final data = await api.get('/billing/pricing') as Map<String, dynamic>;
      setState(() {
        _sale = (data['sale'] as Map<String, dynamic>?) ?? const {};
        _saleActive = _sale['active'] == true;
        _plans = ((data['plans'] as List?) ?? [])
            .map((p) => Map<String, dynamic>.from(p as Map))
            .toList();
        if (_plans.isEmpty) _plans = _fallbackPlans;
      });
    } catch (_) {
      // keep fallback plans
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _checkout(String plan) async {
    final api = context.read<AuthState>().api;
    final promo = _promoController.text.trim();
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final data = await api.post('/billing/checkout', {
        'plan': plan,
        'billing': _yearly ? 'yearly' : 'monthly',
        if (promo.isNotEmpty) 'promo_code': promo,
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

  String _fmt(int cents) {
    final whole = cents ~/ 100;
    final frac = (cents % 100).toString().padLeft(2, '0');
    return '\$$whole.$frac';
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
                  if (_saleActive) ...[
                    const SizedBox(height: 16),
                    _saleBanner(context),
                  ],
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
                  _promoField(context),
                  const SizedBox(height: 8),
                  for (final plan in _plans) ...[
                    _planCard(context, plan),
                    const SizedBox(height: 16),
                  ],
                  if (_error != null) ...[
                    const SizedBox(height: 8),
                    Text(_error!,
                        style: TextStyle(color: Colors.red.shade600)),
                  ],
                ],
              ),
            ),
    );
  }

  Widget _saleBanner(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final code = _sale['code'] as String? ?? 'EARLY40';
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: scheme.primary.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: scheme.primary),
      ),
      child: Row(
        children: [
          Icon(Icons.local_fire_department, color: scheme.primary),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'Early-adopter sale — 40% off your first 3 months. '
              'First 100 subscribers only.',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ),
        ],
      ),
    );
  }

  Widget _promoField(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final entered = _promoController.text.trim().toUpperCase();
    final code = (_sale['code'] as String? ?? 'EARLY40').toUpperCase();
    final matches = entered.isNotEmpty && entered == code;
    return TextField(
      controller: _promoController,
      textCapitalization: TextCapitalization.characters,
      inputFormatters: [
        FilteringTextInputFormatter.allow(RegExp(r'[a-zA-Z0-9]')),
      ],
      decoration: InputDecoration(
        labelText: 'Promo code',
        hintText: 'e.g. $code',
        border: const OutlineInputBorder(),
        isDense: true,
        suffixIcon: matches
            ? Icon(Icons.check_circle, color: Colors.green.shade600)
            : null,
        helperText: matches
            ? '40% off your first 3 months applied at checkout'
            : 'Applied automatically at checkout when entered.',
        helperStyle: TextStyle(
          color: matches ? Colors.green.shade700 : scheme.onSurfaceVariant,
          fontSize: 12,
        ),
      ),
    );
  }

  Widget _planCard(BuildContext context, Map<String, dynamic> plan) {
    final scheme = Theme.of(context).colorScheme;
    final key = plan['key'] as String;
    final name = plan['name'] as String;
    final monthly = plan['monthly'] as int? ?? 900;
    final yearly = plan['yearly'] as int? ?? 8400;
    final saleMonthly = plan['sale_monthly'] as int?;
    final isGarage = key == 'garage';
    final vehicles = isGarage ? 5 : 1;

    final String price;
    final String period;
    if (_yearly) {
      price = _fmt(yearly);
      period = '/year';
    } else if (_saleActive && saleMonthly != null) {
      price = _fmt(saleMonthly);
      period = '/month';
    } else {
      price = _fmt(monthly);
      period = '/month';
    }

    return Card(
      shape: isGarage
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
                if (isGarage)
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
                if (_saleActive && saleMonthly != null && !_yearly) ...[
                  const SizedBox(width: 8),
                  Text(_fmt(monthly),
                      style: TextStyle(
                        color: scheme.onSurfaceVariant,
                        decoration: TextDecoration.lineThrough,
                      )),
                  const SizedBox(width: 6),
                  Chip(
                    label: const Text('40% off'),
                    labelStyle: TextStyle(color: Colors.green.shade800),
                    visualDensity: VisualDensity.compact,
                    side: BorderSide(color: Colors.green.shade400),
                    backgroundColor: Colors.green.withValues(alpha: 0.08),
                  ),
                ],
              ],
            ),
            const SizedBox(height: 4),
            Text('$vehicles vehicle${vehicles == 1 ? '' : 's'}',
                style: Theme.of(context).textTheme.bodySmall),
            const SizedBox(height: 12),
            ..._featuresFor(key).map(
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
                onPressed: _busy ? null : () => _checkout(key),
                child: Text('Upgrade to $name'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  List<String> _featuresFor(String key) {
    return key == 'garage'
        ? const [
            '5 vehicles',
            'All AI features included',
            'Rego lookup',
            'Priority support',
          ]
        : const [
            '1 vehicle',
            'All AI features included',
            'Rego lookup',
          ];
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
      title = 'Subscription active';
      subtitle = 'You have full access to AutoBrain. '
          'Managed by Stripe.';
    } else {
      icon = Icons.info_outline;
      color = Colors.blue;
      title = 'No active subscription';
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
}
