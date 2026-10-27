import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/models.dart';
import '../../services/vass_api.dart';
import 'import_pathway_result_screen.dart';

class ImportPathwayVinScreen extends StatefulWidget {
  const ImportPathwayVinScreen({super.key});

  @override
  State<ImportPathwayVinScreen> createState() => _ImportPathwayVinScreenState();
}

class _ImportPathwayVinScreenState extends State<ImportPathwayVinScreen> {
  late final VassApi _api;
  final _formKey = GlobalKey<FormState>();
  final _vinController = TextEditingController();
  VassJurisdiction _jurisdiction = VassJurisdiction.VIC;
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _api = VassApi(context.read<AuthState>().api);
  }

  @override
  void dispose() {
    _vinController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final res = await _api.createImportPathway(
        ImportPathwayRequest(
          vin: _vinController.text.trim().toUpperCase(),
          jurisdiction: _jurisdiction,
        ),
      );
      if (!mounted) return;
      Navigator.of(context).push(
        MaterialPageRoute(
          builder: (_) => ImportPathwayResultScreen(pathway: res),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e is ApiException ? e.message : '$e';
      });
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Import Pathway Tool')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Form(
          key: _formKey,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              TextFormField(
                controller: _vinController,
                decoration: const InputDecoration(
                  labelText: 'VIN',
                  hintText: 'Enter 17-character VIN',
                ),
                textCapitalization: TextCapitalization.characters,
                maxLength: 17,
                validator: (v) {
                  final s = v?.trim() ?? '';
                  if (s.isEmpty) return 'VIN required';
                  if (s.length != 17) return 'VIN must be 17 characters';
                  return null;
                },
              ),
              const SizedBox(height: 16),
              DropdownButtonFormField<VassJurisdiction>(
                initialValue: _jurisdiction,
                decoration: const InputDecoration(labelText: 'Jurisdiction'),
                items: VassJurisdiction.values
                    .map((j) => DropdownMenuItem(
                          value: j,
                          child: Text(j.value),
                        ))
                    .toList(),
                onChanged: (v) {
                  if (v != null) setState(() => _jurisdiction = v);
                },
              ),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: _loading ? null : _submit,
                child: _loading
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Look up pathway'),
              ),
              if (_error != null) ...[
                const SizedBox(height: 16),
                Text(
                  _error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
