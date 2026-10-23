import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/models.dart';
import '../../services/vass_api.dart';

/// Standalone screen for reviewing and confirming vehicle modifications
/// before running the VASS compliance check.
///
/// Receives vehicle data (vehicleId + modifications) from the wizard shell.
class ModificationChecklistScreen extends StatefulWidget {
  const ModificationChecklistScreen({
    super.key,
    required this.vehicleId,
    this.modifications = const [],
    this.jurisdiction = VassJurisdiction.VIC,
  });

  final String vehicleId;
  final List<ModificationItem> modifications;
  final VassJurisdiction jurisdiction;

  @override
  State<ModificationChecklistScreen> createState() =>
      _ModificationChecklistScreenState();
}

class _ModificationChecklistScreenState
    extends State<ModificationChecklistScreen> {
  late final VassApi _api;
  bool _loading = true;
  String? _error;
  ModificationChecklistResponse? _response;
  final Set<int> _confirmed = <int>{};

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
      final res = await _api.generateModificationChecklist(
        ModificationChecklistRequest(
          vehicleId: widget.vehicleId,
          modifications: widget.modifications,
          jurisdiction: widget.jurisdiction,
        ),
      );
      if (!mounted) return;
      setState(() {
        _response = res;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e is ApiException ? e.message : '$e';
        _loading = false;
      });
    }
  }

  void _toggle(int index) {
    setState(() {
      if (_confirmed.contains(index)) {
        _confirmed.remove(index);
      } else {
        _confirmed.add(index);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Modification Checklist')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Text(_error!, textAlign: TextAlign.center),
                  ),
                )
              : _buildContent(),
    );
  }

  Widget _buildContent() {
    final res = _response!;
    final scheme = Theme.of(context).colorScheme;
    final allConfirmed = res.checklist.isNotEmpty &&
        _confirmed.length == res.checklist.length;

    return Column(
      children: [
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: res.checklist.length,
            itemBuilder: (ctx, i) {
              final item = res.checklist[i];
              final checked = _confirmed.contains(i);
              return Card(
                margin: const EdgeInsets.only(bottom: 8),
                child: CheckboxListTile(
                  value: checked,
                  onChanged: (_) => _toggle(i),
                  title: Text(
                    item.name,
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                  subtitle: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(item.description),
                      if (item.adrReferences.isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text(
                            'ADR: ${item.adrReferences.join(', ')}',
                            style: TextStyle(
                                fontSize: 11, color: scheme.primary),
                          ),
                        ),
                      if (item.vsbReferences.isNotEmpty)
                        Text(
                          'VSB6: ${item.vsbReferences.join(', ')}',
                          style: TextStyle(
                              fontSize: 11, color: scheme.primary),
                        ),
                      if (item.vsiReferences.isNotEmpty)
                        Text(
                          'VSI: ${item.vsiReferences.join(', ')}',
                          style: TextStyle(
                              fontSize: 11, color: scheme.primary),
                        ),
                      if (item.requiresEngineerCertification)
                        Text(
                          'Requires engineering certification',
                          style: TextStyle(
                              fontSize: 11, color: scheme.error),
                        ),
                      if (item.requiresLabTesting)
                        Text(
                          'Requires lab testing',
                          style: TextStyle(
                              fontSize: 11, color: scheme.error),
                        ),
                    ],
                  ),
                  controlAffinity: ListTileControlAffinity.leading,
                ),
              );
            },
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              Text(
                '${_confirmed.length}/${res.checklist.length} confirmed',
                style: Theme.of(context).textTheme.labelLarge,
              ),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: FilledButton(
                  onPressed: allConfirmed ? () => Navigator.of(context).pop() : null,
                  child: const Text('Confirm & Continue'),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
