/// Petrol price map (AUT-1813) with servo-spy favourites selector (AUT-1868).
///
/// Renders cached fuel-price markers for a state on an OpenStreetMap tile
/// layer (flutter_map). Each marker carries a star overlay that reflects the
/// signed-in user's favourited (station + fuel type) combos. Tapping a marker
/// opens a call sheet: brand/name, fuel types + prices, a star to toggle a
/// favourite (idempotent — snackbar confirmed), and, when favourited, a
/// quick-edit of direction + threshold_pct. A legend marks favourited
/// stations.
library;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/models.dart';
import '../../services/fuel_prices_api.dart';

/// A single petrol station cluster: all fuel types/prices for one
/// (station_code, lat, lon). The feed is one row per fuel type, so adjacent
/// rows with the same station collapse into one map marker.
class _StationGroup {
  _StationGroup({
    required this.stationCode,
    required this.stationName,
    required this.brand,
    required this.address,
    required this.latitude,
    required this.longitude,
    required this.fuels,
  });
  final String stationCode;
  final String? stationName;
  final String? brand;
  final String? address;
  final double? latitude;
  final double? longitude;
  final List<FuelPrice> fuels;
}

class PetrolPriceMapScreen extends StatefulWidget {
  const PetrolPriceMapScreen({super.key, this.state = 'NSW'});
  final String state;

  @override
  State<PetrolPriceMapScreen> createState() => _PetrolPriceMapScreenState();
}

class _PetrolPriceMapScreenState extends State<PetrolPriceMapScreen> {
  List<FuelPrice> _prices = const [];
  List<FuelPriceWatchlist> _watchlist = const [];
  bool _loading = true;
  String? _error;

  late final FuelPricesApi _api;

  @override
  void initState() {
    super.initState();
    _api = FuelPricesApi(context.read<AuthState>().api);
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final prices = await _api.listPrices(state: widget.state);
      final watch = await _api.listWatchlist();
      if (mounted) {
        setState(() {
          _prices = prices;
          _watchlist = watch;
        });
      }
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } catch (e) {
      if (mounted) setState(() => _error = e.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  /// Favourite combos keyed `"{station_code}:{fuel_type}"`.
  Set<String> get _favKeys => {
        for (final w in _watchlist) '${w.stationCode}:${w.fuelType}',
      };

  List<_StationGroup> get _stations {
    final byCode = <String, _StationGroup>{};
    for (final p in _prices) {
      final g = byCode.putIfAbsent(p.stationCode, () => _StationGroup(
            stationCode: p.stationCode,
            stationName: p.stationName,
            brand: p.brand,
            address: p.address,
            latitude: p.latitude,
            longitude: p.longitude,
            fuels: [],
          ));
      g.fuels.add(p);
    }
    return byCode.values.toList();
  }

  bool _isStationFavourite(_StationGroup s) =>
      s.fuels.any((f) => _favKeys.contains('${s.stationCode}:${f.fuelType}'));

  void _snack(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  void _openSheet(_StationGroup station) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => _CallSheet(
        station: station,
        initialWatch: _watchlist,
        api: _api,
        onChanged: (wl) => setState(() => _watchlist = wl),
        onSnack: _snack,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final stations = _stations;

    return Scaffold(
      appBar: AppBar(
        title: Text('Petrol prices — ${widget.state}'),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            icon: _loading
                ? const SizedBox.square(
                    dimension: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.refresh),
            onPressed: _loading ? null : _load,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text(_error!,
                        textAlign: TextAlign.center,
                        style: TextStyle(color: scheme.error)),
                  ),
                )
              : Stack(
                  children: [
                    FlutterMap(
                      options: const MapOptions(
                        initialCenter: LatLng(-32.5, 147.0), // NSW centroid
                        initialZoom: 6,
                        interactionOptions: InteractionOptions(
                          flags: InteractiveFlag.all &
                              ~InteractiveFlag.rotate,
                        ),
                      ),
                      children: [
                        TileLayer(
                          urlTemplate:
                              'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                          userAgentPackageName: 'com.autobrainservice.app',
                        ),
                        MarkerLayer(
                          markers: [
                            for (final s in stations)
                              if (s.latitude != null && s.longitude != null)
                                Marker(
                                  point: LatLng(s.latitude!, s.longitude!),
                                  width: 40,
                                  height: 48,
                                  child: _MarkerIcon(
                                    isFavourite: _isStationFavourite(s),
                                    onTap: () => _openSheet(s),
                                  ),
                                ),
                          ],
                        ),
                      ],
                    ),
                    if (stations.any(_isStationFavourite))
                      Positioned(
                        left: 12,
                        top: 12,
                        child: _Legend(
                          count: stations.where(_isStationFavourite).length,
                        ),
                      ),
                    const Positioned(
                      left: 12,
                      bottom: 12,
                      child: _OsmCredit(),
                    ),
                  ],
                ),
    );
  }
}

/// Marker pin with a filled-star overlay when the station has any favourite.
class _MarkerIcon extends StatelessWidget {
  const _MarkerIcon({required this.isFavourite, required this.onTap});
  final bool isFavourite;
  final void Function() onTap;

  @override
  Widget build(BuildContext context) {
    final colour = Theme.of(context).colorScheme.primary;
    return GestureDetector(
      onTap: onTap,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Icon(Icons.location_on,
              size: 34, color: colour.withOpacity(0.9)),
          if (isFavourite)
            const Positioned(
              top: -6,
              right: -6,
              child: Icon(Icons.star, size: 16, color: Colors.amber),
            ),
        ],
      ),
    );
  }
}

class _Legend extends StatelessWidget {
  const _Legend({required this.count});
  final int count;

  @override
  Widget build(BuildContext context) => Material(
        elevation: 2,
        borderRadius: BorderRadius.circular(8),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
          decoration: BoxDecoration(
            color: Theme.of(context)
                .colorScheme
                .surfaceContainerHighest
                .withOpacity(0.9),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.star, size: 16, color: Colors.amber),
              const SizedBox(width: 6),
              Text('$count favourited station'
                  '${count == 1 ? '' : 's'}'),
            ],
          ),
        ),
      );
}

class _OsmCredit extends StatelessWidget {
  const _OsmCredit();
  @override
  Widget build(BuildContext context) => Material(
        elevation: 2,
        borderRadius: BorderRadius.circular(8),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          decoration: BoxDecoration(
            color: Theme.of(context)
                .colorScheme
                .surfaceContainerHighest
                .withOpacity(0.9),
            borderRadius: BorderRadius.circular(8),
          ),
          child: const Text('© OpenStreetMap contributors',
              style: TextStyle(fontSize: 11)),
        ),
      );
}

/// Call sheet: brand/name, fuel types + prices, star toggle, quick-edit.
class _CallSheet extends StatefulWidget {
  const _CallSheet({
    required this.station,
    required this.initialWatch,
    required this.api,
    required this.onChanged,
    required this.onSnack,
  });
  final _StationGroup station;
  final List<FuelPriceWatchlist> initialWatch;
  final FuelPricesApi api;
  final void Function(List<FuelPriceWatchlist>) onChanged;
  final void Function(String) onSnack;

  @override
  State<_CallSheet> createState() => _CallSheetState();
}

class _CallSheetState extends State<_CallSheet> {
  late List<FuelPriceWatchlist> _watch;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _watch = List.from(widget.initialWatch);
  }

  FuelPriceWatchlist? _entryFor(FuelPrice f) {
    for (final w in _watch) {
      if (w.stationCode == f.stationCode && w.fuelType == f.fuelType) return w;
    }
    return null;
  }

  Future<void> _toggle(FuelPrice f) async {
    final existing = _entryFor(f);
    if (_busy) return;
    setState(() => _busy = true);
    try {
      if (existing != null) {
        await widget.api.removeWatch(existing.id);
        setState(() => _watch.removeWhere((w) => w.id == existing.id));
        widget.onChanged(List.from(_watch));
        widget.onSnack('Removed from watch list');
      } else {
        final created = await widget.api.addWatch(
          state: f.state,
          stationCode: f.stationCode,
          fuelType: f.fuelType,
        );
        setState(() => _watch.add(created));
        widget.onChanged(List.from(_watch));
        widget.onSnack('Added to watch list');
      }
    } on ApiException catch (e) {
      widget.onSnack(e.message);
    } catch (e) {
      widget.onSnack(e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _update(FuelPriceWatchlist entry, String direction,
      double thresholdPct) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final updated = await widget.api.addWatch(
        state: entry.state,
        stationCode: entry.stationCode,
        fuelType: entry.fuelType,
        direction: direction,
        thresholdPct: thresholdPct,
      );
      setState(() {
        final i = _watch.indexWhere((w) => w.id == entry.id);
        if (i != -1) _watch[i] = updated;
      });
      widget.onChanged(List.from(_watch));
      widget.onSnack('Alert settings saved');
    } on ApiException catch (e) {
      widget.onSnack(e.message);
    } catch (e) {
      widget.onSnack(e.toString());
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return SizedBox(
      height: 460,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.station.brand ??
                  widget.station.stationName ??
                  'Petrol station',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            if (widget.station.stationName != null &&
                widget.station.stationName != widget.station.brand)
              Text(widget.station.stationName!,
                  style: Theme.of(context).textTheme.bodyMedium),
            if (widget.station.address != null)
              Text(widget.station.address!,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: scheme.onSurfaceVariant.withOpacity(0.8),
                      )),
            const SizedBox(height: 12),
            Expanded(
              child: ListView(
                children: [
                  for (final f in widget.station.fuels) ...[
                    _FuelRow(
                      fuel: f,
                      entry: _entryFor(f),
                      busy: _busy,
                      onToggle: () => _toggle(f),
                    ),
                    if (_entryFor(f) != null)
                      _AlertEditor(
                        entry: _entryFor(f)!,
                        busy: _busy,
                        onUpdate: _update,
                      ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FuelRow extends StatelessWidget {
  const _FuelRow({
    required this.fuel,
    required this.entry,
    required this.busy,
    required this.onToggle,
  });
  final FuelPrice fuel;
  final FuelPriceWatchlist? entry;
  final bool busy;
  final void Function() onToggle;

  @override
  Widget build(BuildContext context) {
    final delta = fuel.priceDeltaPct;
    final isUp = delta != null && delta > 0;
    final deltaColour = delta == null
        ? null
        : (isUp ? Colors.red : Colors.green);
    final deltaText = delta == null
        ? 'no recent change'
        : '${isUp ? '+' : ''}${delta.toStringAsFixed(1)}%';
    return ListTile(
      leading: CircleAvatar(
        radius: 16,
        backgroundColor: Theme.of(context)
            .colorScheme
            .primaryContainer
            .withOpacity(0.5),
        child: Icon(
          delta == null
              ? Icons.show_chart
              : (isUp ? Icons.trending_up : Icons.trending_down),
          size: 18,
          color: deltaColour ?? Theme.of(context).colorScheme.primary,
        ),
      ),
      title: Text(fuel.fuelType),
      subtitle: Text(
          '\$${fuel.price?.toStringAsFixed(1) ?? '—'}  ·  $deltaText'),
      trailing: IconButton(
        icon: Icon(entry == null ? Icons.star_border : Icons.star,
            color: entry == null ? null : Colors.amber),
        tooltip: entry == null ? 'Favourite' : 'Favourited',
        onPressed: busy ? null : onToggle,
      ),
    );
  }
}

class _AlertEditor extends StatelessWidget {
  const _AlertEditor({
    required this.entry,
    required this.busy,
    required this.onUpdate,
  });
  final FuelPriceWatchlist entry;
  final bool busy;
  final Future<void> Function(FuelPriceWatchlist, String, double) onUpdate;

  @override
  Widget build(BuildContext context) {
    var direction = entry.direction;
    final threshold = ValueNotifier<double>(entry.thresholdPct);
    return Padding(
      padding: const EdgeInsets.only(bottom: 8, left: 8, right: 8),
      child: Card(
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: StatefulBuilder(
            builder: (context, setState) => Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Alert me when price moves',
                    style: Theme.of(context).textTheme.bodySmall),
                Row(
                  children: [
                    Expanded(
                      child: DropdownButton<String>(
                        isExpanded: true,
                        value: direction,
                        items: const [
                          DropdownMenuItem(value: 'both', child: Text('Up or down')),
                          DropdownMenuItem(value: 'up', child: Text('Up only')),
                          DropdownMenuItem(value: 'down', child: Text('Down only')),
                        ],
                        onChanged: busy
                            ? null
                            : (v) {
                                direction = v!;
                                setState(() {});
                                onUpdate(entry, direction, threshold.value);
                              },
                      ),
                    ),
                    const SizedBox(width: 8),
                    SizedBox(
                      width: 92,
                      child: TextFormField(
                        initialValue: entry.thresholdPct.toStringAsFixed(1),
                        keyboardType: const TextInputType.numberWithOptions(
                            decimal: true),
                        decoration: const InputDecoration(
                          labelText: 'min %',
                          isDense: true,
                        ),
                        onChanged: (v) => threshold.value =
                            double.tryParse(v) ?? threshold.value,
                        onFieldSubmitted: (v) => onUpdate(
                            entry, direction, threshold.value),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
