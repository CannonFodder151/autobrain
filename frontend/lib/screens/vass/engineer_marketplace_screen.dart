import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/models.dart';
import '../../services/vass/vass_api.dart';

/// Engineer marketplace: search, filter, and request VASS engineers.
class EngineerMarketplaceScreen extends StatefulWidget {
  const EngineerMarketplaceScreen({super.key});

  @override
  State<EngineerMarketplaceScreen> createState() => _EngineerMarketplaceScreenState();
}

class _EngineerMarketplaceScreenState extends State<EngineerMarketplaceScreen> {
  late final VassApi _api;
  bool _loading = true;
  String? _error;
  List<VassEngineer> _engineers = [];

  // Filters
  VassJurisdiction? _filterJurisdiction;
  String? _filterType;
  String? _filterSuburb;

  @override
  void initState() {
    super.initState();
    _api = VassApi(context.read<AuthState>().api);
    _load(refresh: true);
  }

  Future<void> _load({bool refresh = false}) async {
    setState(() => _loading = true);
    try {
      final list = await _api.searchEngineers(
        jurisdiction: _filterJurisdiction,
        engineerType: _filterType,
        suburb: _filterSuburb,
      );
      if (!mounted) return;
      setState(() {
        _engineers = list;
        _loading = false;
        _error = null;
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
        title: const Text('Engineer Marketplace'),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.error_outline, size: 48, color: Colors.red),
                      const SizedBox(height: 12),
                      Text(_error!, textAlign: TextAlign.center),
                      const SizedBox(height: 16),
                      FilledButton.tonal(
                        onPressed: () => _load(refresh: true),
                        child: const Text('Retry'),
                      ),
                    ],
                  ),
                )
              : RefreshIndicator(
                  onRefresh: () => _load(refresh: true),
                  child: Column(
                    children: [
                      _FilterBar(
                        jurisdiction: _filterJurisdiction,
                        engineerType: _filterType,
                        suburb: _filterSuburb,
                        onJurisdictionChanged: (j) {
                          setState(() => _filterJurisdiction = j);
                          _load(refresh: true);
                        },
                        onTypeChanged: (t) {
                          setState(() => _filterType = t);
                          _load(refresh: true);
                        },
                        onSuburbChanged: (s) {
                          setState(() => _filterSuburb = s);
                          _load(refresh: true);
                        },
                      ),
                      Expanded(
                        child: _engineers.isEmpty
                            ? Center(
                                child: Column(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Icon(Icons.engineering, size: 64,
                                        color: Theme.of(context).colorScheme.onSurfaceVariant),
                                    const SizedBox(height: 16),
                                    Text(
                                      'No engineers found',
                                      style: TextStyle(
                                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                                        fontSize: 18,
                                      ),
                                    ),
                                    const SizedBox(height: 8),
                                    const Text('Try adjusting your filters.'),
                                    const SizedBox(height: 16),
                                    FilledButton.tonal(
                                      onPressed: () {
                                        setState(() {
                                          _filterJurisdiction = null;
                                          _filterType = null;
                                          _filterSuburb = null;
                                        });
                                        _load(refresh: true);
                                      },
                                      child: const Text('Clear Filters'),
                                    ),
                                  ],
                                ),
                              )
                            : ListView.builder(
                                padding: const EdgeInsets.all(16),
                                itemCount: _engineers.length,
                                itemBuilder: (ctx, i) =>
                                    _EngineerCard(engineer: _engineers[i]),
                              ),
                      ),
                    ],
                  ),
                ),
    );
  }
}

class _FilterBar extends StatelessWidget {
  const _FilterBar({
    required this.jurisdiction,
    required this.engineerType,
    required this.suburb,
    required this.onJurisdictionChanged,
    required this.onTypeChanged,
    required this.onSuburbChanged,
  });

  final VassJurisdiction? jurisdiction;
  final String? engineerType;
  final String? suburb;
  final ValueChanged<VassJurisdiction?> onJurisdictionChanged;
  final ValueChanged<String?> onTypeChanged;
  final ValueChanged<String?> onSuburbChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Jurisdiction chips
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              FilterChip(
                label: const Text('All States'),
                selected: jurisdiction == null,
                onSelected: (_) => onJurisdictionChanged(null),
              ),
              for (final j in VassJurisdiction.values)
                FilterChip(
                  label: Text(j.name),
                  selected: jurisdiction == j,
                  onSelected: (_) => onJurisdictionChanged(j),
                ),
            ],
          ),
          const SizedBox(height: 8),
          // Type chips
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              FilterChip(
                label: const Text('All Types'),
                selected: engineerType == null,
                onSelected: (_) => onTypeChanged(null),
              ),
              FilterChip(
                label: const Text('Signatory'),
                selected: engineerType == 'signatory',
                onSelected: (_) => onTypeChanged('signatory'),
              ),
              FilterChip(
                label: const Text('Inspector'),
                selected: engineerType == 'inspector',
                onSelected: (_) => onTypeChanged('inspector'),
              ),
              FilterChip(
                label: const Text('Consultant'),
                selected: engineerType == 'consultant',
                onSelected: (_) => onTypeChanged('consultant'),
              ),
            ],
          ),
          const SizedBox(height: 8),
          // Suburb search
          SizedBox(
            height: 40,
            child: TextField(
              decoration: InputDecoration(
                hintText: 'Search by suburb...',
                prefixIcon: const Icon(Icons.search, size: 18),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                contentPadding: const EdgeInsets.symmetric(horizontal: 12),
                isDense: true,
              ),
              onChanged: onSuburbChanged,
            ),
          ),
          const SizedBox(height: 4),
        ],
      ),
    );
  }
}

class _EngineerCard extends StatelessWidget {
  const _EngineerCard({required this.engineer});
  final VassEngineer engineer;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(
                  backgroundColor: scheme.primaryContainer,
                  child: Icon(Icons.engineering, size: 20, color: scheme.primary),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(engineer.name, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16)),
                      Text(
                        '${engineer.jurisdiction.name} · ${engineer.engineerType[0].toUpperCase()}${engineer.engineerType.substring(1)}',
                        style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 12),
                      ),
                    ],
                  ),
                ),
                if (engineer.rating != null)
                  Row(
                    children: [
                      const Icon(Icons.star, color: Colors.amber, size: 14),
                      const SizedBox(width: 2),
                      Text('${engineer.rating!.toStringAsFixed(1)}', style: const TextStyle(fontSize: 12)),
                    ],
                  ),
              ],
            ),
            if (engineer.businessName != null) ...[
              const SizedBox(height: 8),
              Row(
                children: [
                  const Icon(Icons.business, size: 14, color: Colors.grey),
                  const SizedBox(width: 4),
                  Expanded(child: Text(engineer.businessName!, style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 13))),
                ],
              ),
            ],
            if (engineer.specialisations.isNotEmpty) ...[
              const SizedBox(height: 8),
              Wrap(
                spacing: 4,
                runSpacing: 4,
                children: engineer.specialisations.map((s) => Chip(
                  label: Text(s, style: const TextStyle(fontSize: 11)),
                  visualDensity: VisualDensity.compact,
                  materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                )).toList(),
              ),
            ],
            const SizedBox(height: 12),
            Row(
              children: [
                if (engineer.phone != null) ...[
                  Icon(Icons.phone, size: 14, color: scheme.onSurfaceVariant),
                  const SizedBox(width: 4),
                  Text(engineer.phone!, style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
                ],
                if (engineer.email != null) ...[
                  if (engineer.phone != null) const SizedBox(width: 16),
                  Icon(Icons.email, size: 14, color: scheme.onSurfaceVariant),
                  const SizedBox(width: 4),
                  Text(engineer.email!, style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
                ],
              ],
            ),
            const SizedBox(height: 12),
            SizedBox(
              width: double.infinity,
              child: FilledButton.tonal(
                onPressed: () => _requestEngineer(context),
                child: const Text('Request Engineer'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _requestEngineer(BuildContext context) async {
    final api = context.read<AuthState>().api;
    final vassApi = VassApi(api);
    try {
      await vassApi.requestEngineer(engineerId: engineer.id);
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Request sent. The engineer will contact you.')),
      );
    } catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Request failed: $e')),
      );
    }
  }
}