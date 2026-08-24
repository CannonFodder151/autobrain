/// Merch store (AUT-1540): shop the catalogue and check your order history.
/// Payment runs through Stripe Checkout, which collects the shipping address.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/auth_state.dart';

class MerchScreen extends StatefulWidget {
  const MerchScreen({super.key});

  @override
  State<MerchScreen> createState() => _MerchScreenState();
}

class _MerchScreenState extends State<MerchScreen> {
  List<Map<String, dynamic>> _products = [];
  List<Map<String, dynamic>> _orders = [];
  bool _loading = true;
  String? _error;
  String? _busyProduct;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    try {
      final catalog = await api.get('/merch/catalog') as Map<String, dynamic>;
      List<Map<String, dynamic>> orders = [];
      try {
        final data = await api.get('/merch/orders') as List<dynamic>;
        orders = data.map((e) => Map<String, dynamic>.from(e as Map)).toList();
      } catch (_) {
        // Orders are auth-scoped; catalogue still shows if they fail.
      }
      if (!mounted) return;
      setState(() {
        _products = ((catalog['products'] as List?) ?? [])
            .map((p) => Map<String, dynamic>.from(p as Map))
            .toList();
        _orders = orders;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() { _loading = false; _error = 'Could not load the store: $e'; });
    }
  }

  Future<void> _buy(Map<String, dynamic> product) async {
    final api = context.read<AuthState>().api;
    setState(() { _busyProduct = product['id'] as String; _error = null; });
    try {
      final data = await api.post('/merch/checkout', {
        'product_id': product['id'],
        'quantity': 1,
      }) as Map<String, dynamic>;
      final ok = await launchUrl(Uri.parse(data['url'] as String),
          mode: LaunchMode.externalApplication);
      if (!ok && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Could not open the checkout.')));
      }
    } catch (e) {
      if (mounted) setState(() => _error = 'Could not start checkout: $e');
    } finally {
      if (mounted) setState(() => _busyProduct = null);
    }
  }

  String _fmtCents(num cents, String currency) {
    final symbols = {'aud': 'A\$', 'usd': 'US\$', 'nzd': 'NZ\$'};
    return '${symbols[currency.toLowerCase()] ?? '\$'}'
        '${(cents / 100).toStringAsFixed(2)}';
  }

  Widget _productCard(Map<String, dynamic> p) {
    final busy = _busyProduct == p['id'];
    return Card(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          AspectRatio(
            aspectRatio: 16 / 10,
            child: p['id'] == 'beanie'
                ? Image.asset('assets/merch/beanie.png', fit: BoxFit.contain)
                : const Icon(Icons.inventory_2_outlined, size: 64),
          ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(p['name'] as String? ?? '',
                    style: Theme.of(context)
                        .textTheme
                        .titleMedium
                        ?.copyWith(fontWeight: FontWeight.w700)),
                const SizedBox(height: 4),
                Text(p['description'] as String? ?? ''),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Text(
                        _fmtCents(p['amount'] as num? ?? 0,
                            p['currency'] as String? ?? 'aud'),
                        style: Theme.of(context).textTheme.titleMedium),
                    const Spacer(),
                    FilledButton.icon(
                      onPressed: busy ? null : () => _buy(p),
                      icon: busy
                          ? const SizedBox(width: 16, height: 16,
                              child: CircularProgressIndicator(strokeWidth: 2))
                          : const Icon(Icons.shopping_bag_outlined),
                      label: const Text('Buy'),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _orderTile(Map<String, dynamic> o) {
    final ship = (o['shipping_address'] as Map<String, dynamic>?);
    final shipTo = ship == null
        ? null
        : [ship['city'], ship['country']].whereType<String>().join(', ');
    return ListTile(
      leading: const Icon(Icons.local_shipping_outlined),
      title: Text('${o['quantity']}× ${o['product_name']}'),
      subtitle: Text([
        _fmtCents(o['amount_total'] as num? ?? 0, o['currency'] as String? ?? 'aud'),
        if (shipTo != null && shipTo.isNotEmpty) 'Ship to $shipTo',
      ].join(' · ')),
      trailing: Chip(
        label: Text(o['status'] as String? ?? ''),
        backgroundColor: Colors.green.shade100,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Merch store'),
          bottom: const TabBar(tabs: [
            Tab(icon: Icon(Icons.shopping_bag_outlined), text: 'Shop'),
            Tab(icon: Icon(Icons.receipt_long_outlined), text: 'My orders'),
          ]),
        ),
        body: _loading
            ? const Center(child: CircularProgressIndicator())
            : _error != null
                ? Center(child: Padding(padding: const EdgeInsets.all(24), child: Text(_error!)))
                : TabBarView(children: [
                    RefreshIndicator(
                      onRefresh: _load,
                      child: ListView(
                        padding: const EdgeInsets.all(12),
                        children: [
                          for (final p in _products) ...[
                            _productCard(p),
                            const SizedBox(height: 12),
                          ],
                          const Padding(
                            padding: EdgeInsets.symmetric(horizontal: 4),
                            child: Text(
                                'Shipping collected at checkout. Flat rate '
                                'applied automatically.',
                                style: TextStyle(fontSize: 12)),
                          ),
                        ],
                      ),
                    ),
                    _orders.isEmpty
                        ? ListView(children: const [
                            Padding(
                              padding: EdgeInsets.all(32),
                              child: Center(child: Text('No orders yet.')),
                            ),
                          ])
                        : RefreshIndicator(
                            onRefresh: _load,
                            child: ListView.separated(
                              itemCount: _orders.length,
                              separatorBuilder: (_, __) => const Divider(height: 1),
                              itemBuilder: (_, i) => _orderTile(_orders[i]),
                            ),
                          ),
                  ]),
      ),
    );
  }
}
