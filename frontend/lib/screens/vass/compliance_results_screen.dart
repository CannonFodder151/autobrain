import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/models.dart';
import '../../services/vass/vass_api.dart';
import 'pdf_viewer_screen.dart';

/// Full compliance results screen with detailed pass/fail per modification.
class ComplianceResultsScreen extends StatefulWidget {
  const ComplianceResultsScreen({super.key, required this.precheckId});

  final String precheckId;

  @override
  State<ComplianceResultsScreen> createState() => _ComplianceResultsScreenState();
}

class _ComplianceResultsScreenState extends State<ComplianceResultsScreen> {
  late final VassApi _api;
  bool _loading = true;
  String? _error;
  VassPrecheck? _precheck;
  List<VassComplianceResult> _results = [];
  List<CompliancePack> _packs = [];

  @override
  void initState() {
    super.initState();
    _api = VassApi(context.read<AuthState>().api);
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final results = await Future.wait([
        _api.getPrecheck(widget.precheckId),
        _api.getComplianceResults(widget.precheckId),
        _api.listPacks(widget.precheckId),
      ]);
      if (!mounted) return;
      setState(() {
        _precheck = results[0] as VassPrecheck;
        _results = results[1] as List<VassComplianceResult>;
        _packs = results[2] as List<CompliancePack>;
        _loading = false;
      });
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e is ApiException ? e.message : '$e';
          _loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Compliance Results'),
        actions: [
          if (_packs.isNotEmpty)
            IconButton(
              icon: const Icon(Icons.picture_as_pdf),
              tooltip: 'View PDF Pack',
              onPressed: () {
                final pack = _packs.first;
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => PdfViewerScreen(
                      packId: pack.id,
                      title: pack.filename,
                    ),
                  ),
                );
              },
            ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? _ErrorView(message: _error!, onRetry: _load)
              : RefreshIndicator(
                  onRefresh: _load,
                  child: _buildContent(),
                ),
    );
  }

  Widget _buildContent() {
    if (_results.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(32),
          child: Text(
            'No compliance results found.\nRun a pre-check first.',
            textAlign: TextAlign.center,
            style: TextStyle(color: Colors.grey),
          ),
        ),
      );
    }

    final passed = _results.where((r) => r.status == VassComplianceStatus.pass).length;
    final failed = _results.where((r) => r.status == VassComplianceStatus.fail).length;
    final conditional = _results.where((r) => r.status == VassComplianceStatus.conditional).length;
    final total = _results.length;
    final score = total > 0 ? (passed / total * 100).round() : 0;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        // Score overview card
        _ScoreOverview(
          score: score,
          passed: passed,
          conditional: conditional,
          failed: failed,
          total: total,
          jurisdiction: _precheck?.jurisdiction.name ?? 'VIC',
          vehicleLabel: _vehicleLabel(),
        ),
        const SizedBox(height: 20),
        // Reference legend
        if (_hasReferences()) ...[
          _ReferenceLegend(),
          const SizedBox(height: 16),
        ],
        // Results list
        ..._results.map((r) => _DetailedResultCard(result: r)),
        // Packs
        if (_packs.isNotEmpty) ...[
          const SizedBox(height: 16),
          Text(
            'Compliance Packs',
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 8),
          ..._packs.map((p) => _PackCard(pack: p)),
        ],
      ],
    );
  }

  String _vehicleLabel() {
    if (_precheck == null) return '';
    final p = _precheck!;
    return '${p.make ?? ''} ${p.model ?? ''}'.trim();
  }

  bool _hasReferences() {
    return _results.any((r) =>
      r.adrReferences.isNotEmpty ||
      r.vsbReferences.isNotEmpty ||
      r.vsb6References.isNotEmpty);
  }
}

class _ScoreOverview extends StatelessWidget {
  const _ScoreOverview({
    required this.score,
    required this.passed,
    required this.conditional,
    required this.failed,
    required this.total,
    required this.jurisdiction,
    required this.vehicleLabel,
  });

  final int score, passed, conditional, failed, total;
  final String jurisdiction;
  final String vehicleLabel;

  @override
  Widget build(BuildContext context) {
    final color = score >= 80
        ? Colors.green
        : score >= 50
            ? Colors.orange
            : Colors.red;
    final scheme = Theme.of(context).colorScheme;

    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            color.withValues(alpha: 0.15),
            color.withValues(alpha: 0.05),
          ],
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              SizedBox(
                width: 72,
                height: 72,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    CircularProgressIndicator(
                      value: score / 100,
                      strokeWidth: 7,
                      backgroundColor: color.withValues(alpha: 0.15),
                      valueColor: AlwaysStoppedAnimation(color),
                    ),
                    Text(
                      '$score%',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w800,
                        color: color,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      vehicleLabel.isNotEmpty ? vehicleLabel : 'Vehicle Compliance',
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      '$total modification(s) checked · $jurisdiction',
                      style: TextStyle(
                        color: scheme.onSurfaceVariant,
                        fontSize: 13,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),
          Row(
            children: [
              _StatPill(label: 'Pass', count: passed, color: Colors.green),
              const SizedBox(width: 8),
              _StatPill(label: 'Conditional', count: conditional, color: Colors.orange),
              const SizedBox(width: 8),
              _StatPill(label: 'Fail', count: failed, color: Colors.red),
            ],
          ),
        ],
      ),
    );
  }
}

class _StatPill extends StatelessWidget {
  const _StatPill({required this.label, required this.count, required this.color});
  final String label;
  final int count;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(width: 6, height: 6, decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
          const SizedBox(width: 5),
          Text('$count $label', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: color)),
        ],
      ),
    );
  }
}

class _ReferenceLegend extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Reference Key',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w700,
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 12,
            runSpacing: 4,
            children: [
              _LegendItem(code: 'ADR', label: 'Australian Design Rule'),
              _LegendItem(code: 'VSB', label: 'Vehicle Standards Bulletin'),
              _LegendItem(code: 'VSB6', label: 'VSB6 — Securing Cargo'),
            ],
          ),
        ],
      ),
    );
  }
}

class _LegendItem extends StatelessWidget {
  const _LegendItem({required this.code, required this.label});
  final String code;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.primaryContainer,
            borderRadius: BorderRadius.circular(4),
          ),
          child: Text(code, style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700)),
        ),
        const SizedBox(width: 4),
        Text(label, style: const TextStyle(fontSize: 11)),
      ],
    );
  }
}

class _DetailedResultCard extends StatelessWidget {
  const _DetailedResultCard({required this.result});
  final VassComplianceResult result;

  Color _statusColor(VassComplianceStatus status) {
    switch (status) {
      case VassComplianceStatus.pass: return Colors.green;
      case VassComplianceStatus.fail: return Colors.red;
      case VassComplianceStatus.conditional: return Colors.orange;
      case VassComplianceStatus.pending: return Colors.grey;
      case VassComplianceStatus.na: return Colors.grey;
    }
  }

  IconData _statusIcon(VassComplianceStatus status) {
    switch (status) {
      case VassComplianceStatus.pass: return Icons.check_circle;
      case VassComplianceStatus.fail: return Icons.cancel;
      case VassComplianceStatus.conditional: return Icons.warning_amber;
      case VassComplianceStatus.pending: return Icons.hourglass_empty;
      case VassComplianceStatus.na: return Icons.remove_circle_outline;
    }
  }

  @override
  Widget build(BuildContext context) {
    final color = _statusColor(result.status);
    final refs = [
      ...result.adrReferences,
      ...result.vsbReferences,
      ...result.vsb6References,
    ];

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header bar
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            color: color.withValues(alpha: 0.08),
            child: Row(
              children: [
                Icon(_statusIcon(result.status), color: color, size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        result.modificationName,
                        style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15),
                      ),
                      Text(
                        result.category[0].toUpperCase() + result.category.substring(1),
                        style: TextStyle(color: Colors.grey.shade600, fontSize: 12),
                      ),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    result.status.displayName,
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: color,
                    ),
                  ),
                ),
              ],
            ),
          ),
          // References
          if (refs.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 10, 14, 0),
              child: Wrap(
                spacing: 6,
                runSpacing: 4,
                children: refs.map((ref) => Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.surfaceContainerHighest,
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(ref, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600)),
                )).toList(),
              ),
            ),
          // Notes
          if (result.notes != null && result.notes!.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 10, 14, 14),
              child: Text(
                result.notes!,
                style: TextStyle(
                  fontSize: 13,
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                  height: 1.5,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _PackCard extends StatelessWidget {
  const _PackCard({required this.pack});
  final CompliancePack pack;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 8),
      child: ListTile(
        leading: const Icon(Icons.picture_as_pdf, color: Colors.red, size: 28),
        title: Text(pack.filename, style: const TextStyle(fontWeight: FontWeight.w600)),
        subtitle: Text(
          '${pack.passedMods}/${pack.totalMods} passed · '
          'Score: ${pack.overallScore?.round() ?? 0}%',
        ),
        trailing: const Icon(Icons.chevron_right),
        onTap: () {
          Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => PdfViewerScreen(
                packId: pack.id,
                title: pack.filename,
              ),
            ),
          );
        },
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
        padding: const EdgeInsets.all(32),
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