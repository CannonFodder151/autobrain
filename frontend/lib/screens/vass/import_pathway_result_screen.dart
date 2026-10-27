import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/models.dart';
import '../../services/vass_api.dart';

class ImportPathwayResultScreen extends StatefulWidget {
  const ImportPathwayResultScreen({super.key, required this.pathway});

  final ImportPathwayOut pathway;

  @override
  State<ImportPathwayResultScreen> createState() =>
      _ImportPathwayResultScreenState();
}

class _ImportPathwayResultScreenState extends State<ImportPathwayResultScreen> {
  late final VassApi _api;
  bool _loading = true;
  String? _error;
  ImportPathwayDetailOut? _detail;

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
      final res = await _api.getImportPathway(widget.pathway.id);
      if (!mounted) return;
      setState(() {
        _detail = res;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e is ApiException ? e.message : '$e';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.pathway;
    return Scaffold(
      appBar: AppBar(title: Text(p.pathwayType)),

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
    final d = _detail!;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text('VIN: ${d.vin}', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        Text('Eligibility: ${d.eligibility}'),
        const SizedBox(height: 8),
        if (d.vehicleMake != null)
          Text('Vehicle: ${d.vehicleMake} ${d.vehicleModel ?? ''} ${d.vehicleYear ?? ''}'),
        const SizedBox(height: 16),
        Text('Document checklist', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        if (d.documentChecklist.isEmpty)
          const Text('No documents required.')
        else
          ...d.documentChecklist.map(
            (item) => Card(
              margin: const EdgeInsets.only(bottom: 8),
              child: ListTile(
                leading: Icon(
                  item.provided
                      ? Icons.check_circle
                      : item.required
                          ? Icons.radio_button_unchecked
                          : Icons.circle_outlined,
                ),
                title: Text(item.name),
                subtitle: item.description != null ? Text(item.description!) : null,
                trailing: item.required ? const Text('Required') : const Text('Optional'),
              ),
            ),
          ),
      ],
    );
  }
}
