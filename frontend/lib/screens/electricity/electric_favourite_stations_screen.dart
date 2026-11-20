/// Electric Spy Favourite Charging Stations screen (AUT-466c).
///
/// Displays the user's favourite charging stations with connector type, allows
/// removing favourites, and shows historical data on tap.

library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/models.dart';
import '../../services/electric_prices_api.dart';

class ElectricFavouriteStationsScreen extends StatefulWidget {
  const ElectricFavouriteStationsScreen({super.key});

  @override
  State<ElectricFavouriteStationsScreen> createState() => _ElectricFavouriteStationsScreenState();
}

class _ElectricFavouriteStationsScreenState extends State<ElectricFavouriteStationsScreen> {
  bool _loading = true;
  String? _error;
  List<ChargingStationPriceWatchlist> _favourites = const [];

  @override
  void initState() {
    super.initState();
    _loadFavourites();
  }

  Future<void> _loadFavourites() async {
    setState(() => _loading = true);
    try {
      final api = context.read<AuthState>().api;
      final electricApi = ElectricPricesApi(api);
      final favourites = await electricApi.listWatchlist();
      if (!mounted) return;
      setState(() {
        _favourites = favourites;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = 'Could not load favourites (${e.statusCode}).';
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _error = 'Could not load favourites. Check your connection.';
        _loading = false;
      });
    }
  }

  Future<void> _removeFavourite(ChargingStationPriceWatchlist fav) async {
    try {
      final api = context.read<AuthState>().api;
      final electricApi = ElectricPricesApi(api);
      await electricApi.removeWatch(fav.id);
      if (!mounted) return;
      setState(() {
        _favourites = _favourites.where((f) => f.id != fav.id).toList();
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Removed ${fav.stationName ?? fav.stationId} (${fav.connectorType})')),
      );
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Failed to remove favourite (${e.statusCode})')),
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Failed to remove favourite')),
      );
    }
  }

  Future<void> _openAddStation() async {
    final scheme = Theme.of(context).colorScheme;
    final stationIdCtrl = TextEditingController();
    final stationNameCtrl = TextEditingController();
    final brandCtrl = TextEditingController();
    String connectorType = 'CCS2';
    String direction = 'both';
    double thresholdPct = 5.0;
    bool busy = false;

    final connectorTypes = ['CCS2', 'CHAdeMO', 'Type 2', 'Tesla', 'GB/T'];
    final directions = ['both', 'up', 'down'];

    await showDialog<void>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: const Text('Add charging station to watchlist'),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: stationIdCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Station ID *',
                    hintText: 'e.g. AU-NSW-SYD-001',
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: stationNameCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Station name (optional)',
                    hintText: 'e.g. Tesla Supercharger Sydney',
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: brandCtrl,
                  decoration: const InputDecoration(
                    labelText: 'Brand (optional)',
                    hintText: 'e.g. Tesla, Chargefox, Evie',
                  ),
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  value: connectorType,
                  decoration: const InputDecoration(labelText: 'Connector type'),
                  items: connectorTypes
                      .map((c) => DropdownMenuItem(value: c, child: Text(c)))
                      .toList(),
                  onChanged: (v) => setDialogState(() => connectorType = v!),
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  value: direction,
                  decoration: const InputDecoration(labelText: 'Alert direction'),
                  items: directions
                      .map((d) => DropdownMenuItem(value: d, child: Text(d == 'both' ? 'Up or down' : d == 'up' ? 'Price up' : 'Price down')))
                      .toList(),
                  onChanged: (v) => setDialogState(() => direction = v!),
                ),
                const SizedBox(height: 12),
                TextFormField(
                  initialValue: thresholdPct.toString(),
                  decoration: const InputDecoration(
                    labelText: 'Threshold %',
                    hintText: 'e.g. 5.0',
                  ),
                  keyboardType: TextInputType.numberWithOptions(decimal: true),
                  onChanged: (v) => thresholdPct = double.tryParse(v) ?? 5.0,
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: busy ? null : () => Navigator.pop(ctx),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: busy
                  ? null
                  : () async {
                      final id = stationIdCtrl.text.trim();
                      if (id.isEmpty) return;
                      setDialogState(() => busy = true);
                      try {
                        final api = context.read<AuthState>().api;
                        final electricApi = ElectricPricesApi(api);
                        await electricApi.addWatch(
                          stationId: id,
                          stationName: stationNameCtrl.text.trim().isEmpty ? null : stationNameCtrl.text.trim(),
                          brand: brandCtrl.text.trim().isEmpty ? null : brandCtrl.text.trim(),
                          connectorType: connectorType,
                          direction: direction,
                          thresholdPct: thresholdPct,
                        );
                        if (!mounted) return;
                        Navigator.pop(ctx);
                        _loadFavourites();
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(content: Text('Added $id to watchlist')),
                        );
                      } on ApiException catch (e) {
                        if (!mounted) return;
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(content: Text('Failed to add (${e.statusCode})')),
                        );
                      } catch (_) {
                        if (!mounted) return;
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Failed to add')),
                        );
                      } finally {
                        if (mounted) setDialogState(() => busy = false);
                      }
                    },
              child: busy ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2)) : const Text('Add'),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Favourite Charging Stations'),
        actions: [
          IconButton(
            tooltip: 'Add station',
            icon: const Icon(Icons.add),
            onPressed: _openAddStation,
          ),
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: _loadFavourites,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.error_outline, size: 48, color: scheme.error),
                        const SizedBox(height: 12),
                        Text(_error!, textAlign: TextAlign.center),
                        const SizedBox(height: 16),
                        FilledButton.tonal(onPressed: _loadFavourites, child: const Text('Retry')),
                      ],
                    ),
                  ),
                )
              : _favourites.isEmpty
                  ? Center(
                      child: Padding(
                        padding: const EdgeInsets.all(32),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.favorite_border, size: 56, color: scheme.onSurfaceVariant),
                            const SizedBox(height: 16),
                            Text('No favourite stations yet', style: Theme.of(context).textTheme.titleMedium),
                            const SizedBox(height: 8),
                            Text(
                              'Tap "Watch price" on a charging station to add it to your favourites.',
                              textAlign: TextAlign.center,
                              style: TextStyle(color: scheme.onSurfaceVariant),
                            ),
                          ],
                        ),
                      ),
                    )
                  : ListView.builder(
                      padding: const EdgeInsets.all(16),
                      itemCount: _favourites.length,
                      itemBuilder: (ctx, i) {
                        final fav = _favourites[i];
                        return Card(
                          child: ListTile(
                            leading: CircleAvatar(
                              backgroundColor: scheme.surfaceContainerHighest,
                              child: Text(
                                (fav.brand ?? fav.stationName ?? fav.stationId).substring(0, 1).toUpperCase(),
                                style: TextStyle(color: scheme.onSurfaceVariant),
                              ),
                            ),
                            title: Text(fav.stationName ?? fav.stationId),
                            subtitle: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                if (fav.brand != null) Text(fav.brand!),
                                Text('Connector: ${fav.connectorType}'),
                              ],
                            ),
                            trailing: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                IconButton(
                                  tooltip: 'Remove favourite',
                                  icon: const Icon(Icons.favorite, color: Colors.red),
                                  onPressed: () => _removeFavourite(fav),
                                ),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
    );
  }
}