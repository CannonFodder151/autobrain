import 'dart:ui' show TargetPlatform;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:in_app_purchase/in_app_purchase.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/auth_state.dart';
import '../../core/config.dart';
import '../../services/iap_service.dart';

/// Stripe subscription management: current plan + upgrade/downgrade/cancel.
/// Prices come from GET /billing/pricing (with the early-adopter sale); the
/// values below are a fallback for hosts that do not expose /billing/pricing.
/// For store builds, IAP plans are shown when enabled and products are available.
class LicenseScreen extends StatefulWidget {
  const LicenseScreen({super.key});

  @override
  State<LicenseScreen> createState() => _LicenseScreenState();
}

class _LicenseScreenState extends State<LicenseScreen> {
  static const _fallbackPlans = [
    {'key': 'enthusiast', 'name': 'Enthusiast', 'monthly': 590, 'yearly': 5900},
    {'key': 'garage', 'name': 'Garage', 'monthly': 1190, 'yearly': 11900},
  ];

  final _promoController = TextEditingController();

  Map<String, dynamic>? _profile;
  List<Map<String, dynamic>> _plans = _fallbackPlans;
  Map<String, dynamic> _sale = const {};
  String _currency = 'aud';
  bool _saleActive = false;
  bool _iapMode = false;
  bool _loading = true;
  bool _yearly = false;
  bool _busy = false;
  String? _error;
  IapService? _iapService;

  String? get _subStatus => _profile?['subscription_status'] as String?;
  String? get _licenseStatus {
    final s = _profile?['license_status'] as String?;
    if (s != null) return s;
    final sub = _subStatus;
    if (sub == 'active' || sub == 'trialing' || sub == 'past_due') return 'active';
    if (sub == 'incomplete' || sub == 'incomplete_expired' || sub == 'unpaid') {
      return 'pending';
    }
    return 'free';
  }

  bool get _hasSub => _licenseStatus == 'active';
  bool get _hasPending => _licenseStatus == 'pending';
  int get _maxVehicles => (_profile?['max_vehicles'] as int?) ?? 1;

  /// One-time 7-day free trial (AUT-1195): the backend offers it on monthly
  /// plans while the account has not used its trial yet, via the /auth/me
  /// payload (`trial_available` / `trial_days`). Surfaced for both the Stripe
  /// checkout path and the store (IAP) path, where the native subscription
  /// base plan carries the free trial (AUT-1771). Hidden on yearly and once
  /// the trial was used.
  bool get _trialAvailable =>
      !_hasSub && _profile?['trial_available'] == true;
  int get _trialDays =>
      (_profile?['trial_days'] as int?) ?? (_trialAvailable ? 7 : 0);

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _onIapPurchase(PurchaseDetails purchase) {
    if (!mounted) return;
    if (purchase.status == PurchaseStatus.purchased ||
        purchase.status == PurchaseStatus.restored) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Purchase verified. Refreshing...')),
      );
      _load(); // refresh profile to reflect new entitlement
    } else if (purchase.status == PurchaseStatus.error) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Purchase failed: ${purchase.error}')),
      );
    } else if (purchase.status == PurchaseStatus.canceled) {
      // User dismissed the store dialog — no feedback needed.
    }
    if (mounted) setState(() => _busy = false);
  }

  @override
  void dispose() {
    _promoController.dispose();
    _iapService?.dispose();
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
      setState(() {
        _profile = me;
        if (_error != null) _error = null;
      });
    } catch (_) {
      // Keep _error set to show auth failure, but allow plans to load
    }
    bool iapAvailable = false;
    // IAP mode is for the native Android/iOS app only (AUT-1224). On the web
    // build the catalog check must never run: `Theme.of(context).platform`
    // resolves to a non-iOS target on desktop browsers, which then matched the
    // android products from the hosted catalog and swapped the Stripe plan
    // cards for "Buy from Store" buttons with hardcoded prices. Native mobile
    // keeps IAP; the website always uses the Stripe checkout path.
    if (AppConfig.isMobile) {
      try {
        final catalog = await api.get('/billing/iap/catalog') as Map<String, dynamic>;
        final enabled = catalog['enabled'] == true;
        if (enabled) {
          final products = (catalog['products'] as List?) ?? [];
          if (products.isNotEmpty) {
            final currentPlatform = Theme.of(context).platform == TargetPlatform.iOS ? 'ios' : 'android';
            final iapPlans = products
                .where((p) => (p as Map)['platform'] == currentPlatform)
                .toList()
                .cast<Map<String, dynamic>>();
            if (iapPlans.isNotEmpty) {
              setState(() {
                _iapMode = true;
                _plans = iapPlans;
              });
              iapAvailable = true;
              // Initialize native IAP billing for Play Store / App Store purchases.
              if (_iapService == null) {
                _iapService = IapService(context.read<AuthState>());
                _iapService!.purchaseStream.listen(_onIapPurchase);
                final ids = iapPlans.map((p) => p['product_id'] as String).toList();
                await _iapService!.init(ids);
              }
            }
          }
        }
      } catch (_) {
        // IAP endpoint not available, fall back to Stripe pricing
      }
    }
    if (!iapAvailable) {
      try {
        final data = await api.get('/billing/pricing') as Map<String, dynamic>;
        setState(() {
          _iapMode = false;
          _currency = (data['currency'] as String?) ?? 'aud';
          _sale = (data['sale'] as Map<String, dynamic>?) ?? const {};
          _saleActive = _sale['active'] == true;
          _plans = ((data['plans'] as List?) ?? [])
              .map((p) => Map<String, dynamic>.from(p as Map))
              .toList();
          if (_plans.isEmpty) _plans = _fallbackPlans;
        });
      } catch (_) {
        // keep fallback plans
      }
    }
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _checkout(String plan, [Map<String, dynamic>? planData]) async {
    final api = context.read<AuthState>().api;
    final promo = _promoController.text.trim();
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      // Use native store purchase when IAP is available.
      if (_iapMode && _iapService != null && _iapService!.available) {
        final productId = planData != null
            ? (planData['product_id'] as String? ?? '')
            : '';
        if (productId.isEmpty || !_iapService!.products.containsKey(productId)) {
          setState(() => _error = 'Product not found in store.');
          return;
        }
        final launched = await _iapService!.buy(productId);
        if (!launched) {
          setState(() => _error = 'Could not start store purchase.');
        }
        return;
      }
      // Fallback to Stripe browser checkout.
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
      final data = await api.post('/billing/portal') as Map<String, dynamic>;
      await _openUrl(data['url'] as String);
    } catch (e) {
      setState(() => _error = 'Could not open billing: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _openUrl(String url) async {
    final ok = await launchUrl(Uri.parse(url), mode: LaunchMode.externalApplication);
    if (!ok && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not open the link.')),
      );
    }
  }

  String _fmt(int cents) {
    final whole = cents ~/ 100;
    final frac = (cents % 100).toString().padLeft(2, '0');
    final symbol = _currency == 'aud' ? 'A\$' : '\$';
    return '$symbol$whole.$frac';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('License')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? _buildErrorState()
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(
                    padding: const EdgeInsets.all(16),
                    children: [
                      _statusCard(context),
                      if (_iapMode) ...[
                        const SizedBox(height: 16),
                        _iapBanner(context),
                      ] else if (_saleActive) ...[
                        const SizedBox(height: 16),
                        _saleBanner(context),
                      ],
                      const SizedBox(height: 20),
                      Text(_iapMode ? 'Plans' : 'Upgrade Plans',
                          style: Theme.of(context)
                              .textTheme
                              .titleMedium
                              ?.copyWith(fontWeight: FontWeight.w700)),
                      const SizedBox(height: 4),
                      Text(_iapMode
                          ? 'Buy from the App Store or Play Store. '
                              'Your subscription stays upgraded until the end of the period.'
                          : 'Upgrade any time — billed monthly or yearly by Stripe. '
                              'Cancel from your billing portal; your account stays '
                              'upgraded until the end of the period.',
                          style: Theme.of(context).textTheme.bodySmall),
                      const SizedBox(height: 12),
                      if (!_iapMode) ...[
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
                              onSelectionChanged: (s) => setState(() => _yearly = s.first),
                            ),
                          ],
                        ),
                        const SizedBox(height: 16),
                        _promoField(context),
                        const SizedBox(height: 8),
                      ],
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

  Widget _buildErrorState() {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _statusCard(context),
        const SizedBox(height: 20),
        Center(
          child: Column(
            children: [
              const Icon(Icons.error_outline, size: 48, color: Colors.grey),
              const SizedBox(height: 16),
              Text(_error ?? 'Error loading plans'),
              const SizedBox(height: 16),
              FilledButton(onPressed: _load, child: const Text('Retry')),
            ],
          ),
        ),
      ],
    );
  }

  Widget _iapBanner(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: scheme.primary.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: scheme.primary),
      ),
      child: Row(
        children: [
          Icon(Icons.storefront, color: scheme.primary),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'Upgrade through the App Store or Play Store. '
              'Manage your subscription in your device settings.',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
          ),
        ],
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
    String key, name;
    int monthly, yearly;
    int? saleMonthly;
    final isGarage;

    if (_iapMode) {
      key = plan['plan'] as String? ?? 'enthusiast';
      name = key == 'garage' ? 'Garage' : 'Enthusiast';
      isGarage = key == 'garage';
      monthly = 1190;
      yearly = 11900;
      saleMonthly = null;
    } else {
      key = plan['key'] as String;
      name = plan['name'] as String;
      monthly = plan['monthly'] as int? ?? 590;
      yearly = plan['yearly'] as int? ?? 5900;
      saleMonthly = plan['sale_monthly'] as int?;
      isGarage = key == 'garage';
    }
    final vehicles = isGarage ? 5 : 1;
    final showTrial = _trialAvailable && !_yearly;

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
                if (showTrial) ...[
                  const SizedBox(width: 8),
                  Chip(
                    label: Text('$_trialDays days free'),
                    labelStyle: TextStyle(color: Colors.green.shade800),
                    visualDensity: VisualDensity.compact,
                    side: BorderSide(color: Colors.green.shade400),
                    backgroundColor: Colors.green.withValues(alpha: 0.08),
                  ),
                ],
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
            if (showTrial)
              Text(
                'Free for $_trialDays days, then billed monthly. '
                'Cancel any time during the trial.',
                style: Theme.of(context).textTheme.bodySmall,
              ),
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
                onPressed: _busy ? null : () => _checkout(key, plan),
                child: Text(_iapMode
                    ? (showTrial
                        ? 'Start your $_trialDays-day free trial'
                        : 'Buy from Store')
                    : showTrial
                        ? 'Start your $_trialDays-day free trial'
                        : 'Upgrade to $name'),
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
          '${_iapMode ? 'Managed by App Store / Play Store.' : 'Managed by Stripe.'}';
    } else if (_hasPending) {
      icon = Icons.hourglass_top;
      color = Colors.orange;
      title = 'License pending';
      subtitle = 'Your licence payment has not been confirmed yet. '
          'Finish the checkout, or try upgrading again.';
    } else {
      icon = Icons.info_outline;
      color = Colors.blue;
      title = 'No active subscription';
      subtitle = '$_maxVehicles vehicle, no AI. '
          'Upgrade for rego lookup and more vehicles.'
          '${_trialAvailable ? ' Monthly plans start with a $_trialDays-day free trial.' : ''}';
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