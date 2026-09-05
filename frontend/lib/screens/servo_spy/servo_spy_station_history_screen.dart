/// 30-day fuel-price history chart for a single Servo Spy station (AUT-2376).
///
/// Uses [FuelPricesApi.stationHistory] (AUT-2374 endpoint). Renders one
/// [AreaChart] line per fuel type using [fl_chart]. Handles the empty case
/// (new station, no history yet) with a subtle illustration.

library;

import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../services/fuel_prices_api.dart';

/// Distinct colours per canonical fuel type — consistent with the green Servo
/// Spy palette for primary fuel, muted tones for the rest.
const _fuelColors = <String, Color>{
  'E10': Color(0xFF57F287),
  '91': Color(0xFF008C45),
  '95': Color(0xFF3A86FF),
  '98': Color(0xFFFF6B6B),
  'Diesel': Color(0xFFFFA94D),
  'LPG': Color(0xFFCC5DE8),
};

class ServoSpyStationHistoryScreen extends StatefulWidget {
  const ServoSpyStationHistoryScreen({
    super.key,
    required this.stationId,
    required this.stationName,
  });

  final String stationId;
  final String stationName;

  @override
  State<ServoSpyStationHistoryScreen> createState() =>
      _ServoSpyStationHistoryScreenState();
}

class _ServoSpyStationHistoryScreenState
    extends State<ServoSpyStationHistoryScreen> {
  bool _loading = true;
  String? _error;
  StationPriceHistory? _history;

  // In-memory cache so re-opening the same station is instant (AUT-2376 §3).
  static final _cache = <String, StationPriceHistory>{};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    // Serve cache first (requirement §3).
    final cached = _cache[widget.stationId];
    if (cached != null) {
      setState(() {
        _history = cached;
        _loading = false;
      });
      return;
    }

    setState(() {
      _loading = true;
      _error = null;
    });

    try {
      final api = context.read<AuthState>().api;
      final pricesApi = FuelPricesApi(api);
      final history = await pricesApi.stationHistory(widget.stationId);
      _cache[widget.stationId] = history;
      if (!mounted) return;
      setState(() {
        _history = history;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = 'Could not load price history (${e.statusCode}).';
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _error = 'Could not load price history.';
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.stationName),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: _load,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? _ErrorView(message: _error!, onRetry: _load)
              : _history == null || _history!.isEmpty
                  ? const _EmptyView()
                  : _ChartView(history: _history!),
    );
  }
}

class _ChartView extends StatelessWidget {
  const _ChartView({required this.history});
  final StationPriceHistory history;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final seriesWithPoints =
        history.series.where((s) => s.points.isNotEmpty).toList();
    if (seriesWithPoints.isEmpty) return const _EmptyView();

    // Flatten all dates for axis bounds.
    final allDates = [
      for (final s in seriesWithPoints) ...s.points.map((p) => p.date),
    ]..sort();
    final minDate = allDates.first;
    final maxDate = allDates.last;
    final daySpan = maxDate.difference(minDate).inDays;

    // Build FlSpot lines per fuel type, x = days-since-start.
    final barData = <LineChartBarData>[];
    final legends = <_LegendEntry>[];

    for (final s in seriesWithPoints) {
      final spots = <FlSpot>[
        for (final p in s.points)
          FlSpot(
            p.date.difference(minDate).inDays.toDouble(),
            p.priceCents,
          ),
      ]
        ..sort((a, b) => a.x.compareTo(b.x));
      final color = _fuelColors[s.fuelType] ?? scheme.primary;
      barData.add(LineChartBarData(
        spots: spots,
        isCurved: true,
        color: color,
        barWidth: 2.5,
        dotData: const FlDotData(show: false),
        belowBarData: BarAreaData(
          show: true,
          color: color.withValues(alpha: 0.12),
        ),
      ));
      legends.add(_LegendEntry(fuelType: s.fuelType, color: color));
    }

    // Y-axis padding: 5% above/below min/max.
    double? minY, maxY;
    for (final s in seriesWithPoints) {
      for (final p in s.points) {
        if (minY == null || p.priceCents < minY) minY = p.priceCents;
        if (maxY == null || p.priceCents > maxY) maxY = p.priceCents;
      }
    }
    final yPad = ((maxY! - minY!) * 0.05).clamp(1.0, 10.0);
    minY -= yPad;
    maxY += yPad;

    final dateFormat = daySpan > 14 ? DateFormat('d MMM') : DateFormat('d/MM');

    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 16, 16, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: Text(
              'Price history — last 30 days',
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
          const SizedBox(height: 12),
          // Legend row.
          Wrap(
            spacing: 14,
            runSpacing: 4,
            children: [
              for (final l in legends)
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 12,
                      height: 12,
                      decoration: BoxDecoration(
                        color: l.color,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 4),
                    Text(l.fuelType, style: const TextStyle(fontSize: 12)),
                  ],
                ),
            ],
          ),
          const SizedBox(height: 12),
          // Chart card.
          Expanded(
            child: Card(
              child: Padding(
                padding:
                    const EdgeInsets.only(left: 8, right: 16, top: 12, bottom: 8),
                child: LineChart(
                  LineChartData(
                    minY: minY,
                    maxY: maxY,
                    minX: 0,
                    maxX: daySpan.toDouble().clamp(1, double.infinity),
                    gridData: FlGridData(
                      show: true,
                      drawVerticalLine: false,
                      horizontalInterval: _yInterval(minY, maxY),
                      getDrawingHorizontalLine: (v) => FlLine(
                        color: scheme.outlineVariant.withValues(alpha: 0.3),
                        strokeWidth: 1,
                      ),
                    ),
                    titlesData: FlTitlesData(
                      topTitles: const AxisTitles(),
                      rightTitles: const AxisTitles(),
                      leftTitles: AxisTitles(
                        sideTitles: SideTitles(
                          showTitles: true,
                          reservedSize: 48,
                          getTitlesWidget: (v, _) => Text(
                            '\$${(v / 100).toStringAsFixed(2)}',
                            style: const TextStyle(fontSize: 10),
                          ),
                        ),
                      ),
                      bottomTitles: AxisTitles(
                        sideTitles: SideTitles(
                          showTitles: true,
                          reservedSize: 28,
                          interval: (daySpan / 5).clamp(1, double.infinity).toDouble(),
                          getTitlesWidget: (v, _) {
                            final d = minDate.add(Duration(days: v.toInt()));
                            return Padding(
                              padding: const EdgeInsets.only(top: 4),
                              child: Text(
                                dateFormat.format(d),
                                style: const TextStyle(fontSize: 10),
                              ),
                            );
                          },
                        ),
                      ),
                    ),
                    borderData: FlBorderData(show: false),
                    lineBarsData: barData,
                    lineTouchData: LineTouchData(
                      touchTooltipData: LineTouchTooltipData(
                        getTooltipItems: (spots) {
                          final date = minDate.add(
                              Duration(days: spots.first.x.toInt()));
                          final lines = spots.map((sp) {
                            final series = seriesWithPoints.firstWhere(
                              (s) =>
                                  s.points.any((p) =>
                                      p.date
                                          .difference(minDate)
                                          .inDays
                                          .toDouble() ==
                                      sp.x),
                              orElse: () => seriesWithPoints.first,
                            );
                            return LineTooltipItem(
                              '${series.fuelType}  \$${(sp.y / 100).toStringAsFixed(2)}',
                              TextStyle(
                                color: _fuelColors[series.fuelType] ??
                                    scheme.primary,
                                fontWeight: FontWeight.w600,
                                fontSize: 12,
                              ),
                            );
                          }).toList();
                          return [
                            LineTooltipItem(
                              DateFormat('d MMM').format(date),
                              TextStyle(
                                color: scheme.onSurface,
                                fontSize: 11,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                            ...lines,
                          ];
                        },
                      ),
                      handleBuiltInTouches: true,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// Nice Y-axis interval: aim for ~5 ticks.
  static double _yInterval(double? min, double? max) {
    if (min == null || max == null) return 10;
    final range = max - min;
    if (range <= 0) return 5;
    final rough = range / 5;
    final mag = math.pow(rough, rough.floorToDouble()).toDouble();
    final norm = rough / mag;
    final nice = norm < 1.5
        ? 1
        : norm < 3.5
            ? 2
            : norm < 7.5
                ? 5
                : 10;
    return nice * mag;
  }
}

class _LegendEntry {
  final String fuelType;
  final Color color;
  const _LegendEntry({required this.fuelType, required this.color});
}

class _EmptyView extends StatelessWidget {
  const _EmptyView();

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.show_chart, size: 48, color: scheme.onSurfaceVariant),
            const SizedBox(height: 12),
            Text(
              'No price history yet',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            Text(
              'Prices will appear here after the first day of data is recorded.',
              textAlign: TextAlign.center,
              style: TextStyle(color: scheme.onSurfaceVariant),
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline, size: 48, color: scheme.error),
            const SizedBox(height: 12),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 16),
            FilledButton.tonal(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}
