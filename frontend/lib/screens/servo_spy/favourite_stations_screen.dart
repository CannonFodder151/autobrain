/// Favourite Fuel Stations screen (AUT-4556).
///
/// Displays the user's favourite fuel stations with fuel type, allows
/// removing favourites, and shows historical data on tap.

library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/models.dart';
import '../../services/fuel_prices_api.dart';
import 'servo_spy_station_history_screen.dart';

class FavouriteStationsScreen extends StatefulWidget {
  const FavouriteStationsScreen({super.key});

  @override
  State<FavouriteStationsScreen> createState() => _FavouriteStationsScreenState();
}

class _FavouriteStationsScreenState extends State<FavouriteStationsScreen> {
  bool _loading = true;
  String? _error;
  List<FuelPriceWatchlist> _favourites = const [];

  @override
  void initState() {
    super.initState();
    _loadFavourites();
  }

  Future<void> _loadFavourites() async {
    setState(() => _loading = true);
    try {
      final api = context.read<AuthState>().api;
      final fuelApi = FuelPricesApi(api);
      final favourites = await fuelApi.listWatchlist();
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

  Future<void> _removeFavourite(FuelPriceWatchlist fav) async {
    try {
      final api = context.read<AuthState>().api;
      final fuelApi = FuelPricesApi(api);
      await fuelApi.removeWatch(fav.id);
      if (!mounted) return;
      setState(() {
        _favourites = _favourites.where((f) => f.id != fav.id).toList();
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Removed ${fav.stationName ?? fav.stationCode} (${fav.fuelType})')),
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

  void _openHistory(FuelPriceWatchlist fav) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (_) => ServoSpyStationHistoryScreen(
          stationId: fav.stationCode,
          stationName: fav.stationName ?? fav.stationCode,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Favourite Fuel Stations'),
        actions: [
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
                              'Tap the star on a station to add it to your favourites.',
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
                                (fav.brand ?? fav.stationName ?? fav.stationCode).substring(0, 1).toUpperCase(),
                                style: TextStyle(color: scheme.onSurfaceVariant),
                              ),
                            ),
                            title: Text(fav.stationName ?? fav.stationCode),
                            subtitle: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                if (fav.brand != null) Text(fav.brand!),
                                Text('Fuel: ${fav.fuelType}  ·  ${fav.state}'),
                              ],
                            ),
                            trailing: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                IconButton(
                                  tooltip: 'View history',
                                  icon: const Icon(Icons.history),
                                  onPressed: () => _openHistory(fav),
                                ),
                                IconButton(
                                  tooltip: 'Remove favourite',
                                  icon: const Icon(Icons.favorite, color: Colors.red),
                                  onPressed: () => _removeFavourite(fav),
                                ),
                              ],
                            ),
                            onTap: () => _openHistory(fav),
                          ),
                        );
                      },
                    ),
    );
  }
}