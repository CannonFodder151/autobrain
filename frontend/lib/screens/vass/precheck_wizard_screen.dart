import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/models.dart';
import '../../services/vass/vass_api.dart';
import 'compliance_results_screen.dart';
import 'pdf_viewer_screen.dart';

/// Multi-step VASS pre-check wizard.
///
/// Steps:
/// 1. Vehicle info (make/model/year + VIN)
/// 2. Modification checklist
/// 3. Jurisdiction selection
/// 4. Run check → results
class PrecheckWizardScreen extends StatefulWidget {
  const PrecheckWizardScreen({super.key, this.vehicleId});

  final String? vehicleId;

  @override
  State<PrecheckWizardScreen> createState() => _PrecheckWizardScreenState();
}

class _PrecheckWizardScreenState extends State<PrecheckWizardScreen> {
  late final VassApi _api;
  int _step = 0;
  bool _busy = false;
  String? _error;

  // Form data
  VassJurisdiction _jurisdiction = VassJurisdiction.VIC;
  final _vinController = TextEditingController();
  final _makeController = TextEditingController();
  final _modelController = TextEditingController();
  final _yearController = TextEditingController();
  String _bodyType = 'Sedan';
  final _engineController = TextEditingController();
  final _transmissionController = TextEditingController();
  final List<ModificationSelection> _modifications = [];

  VassPrecheck? _createdPrecheck;
  List<VassComplianceResult> _results = [];

  static const _bodyTypes = [
    'Sedan', 'Hatchback', 'SUV', 'Ute', 'Coupe', 'Wagon',
    'Convertible', 'Van', 'Truck', 'Motorcycle', 'Other',
  ];

  static const _modCategories = [
    'performance', 'engine', 'exhaust', 'suspension', 'brakes',
    'audio', 'visual', 'interior', 'exterior', 'other',
  ];

  @override
  void initState() {
    super.initState();
    _api = VassApi(context.read<AuthState>().api);
    _loadVehicleDefaults();
  }

  Future<void> _loadVehicleDefaults() async {
    if (widget.vehicleId == null) return;
    try {
      final cached = await context.read<AuthState>().api.getCachedDecoded('/vehicles', null);
      if (cached == null) return;
      final vehicles = (cached as List)
          .map((e) => Vehicle.fromJson(e as Map<String, dynamic>))
          .toList();
      final v = Vehicle.byId(vehicles, widget.vehicleId!);
      if (v == null || !mounted) return;
      setState(() {
        _makeController.text = v.make ?? '';
        _modelController.text = v.model ?? '';
        _yearController.text = v.year?.toString() ?? '';
        _vinController.text = v.vin ?? '';
        _engineController.text = v.engine ?? '';
        _transmissionController.text = v.transmission ?? '';
        if (v.bodyType != null) _bodyType = v.bodyType!;
      });
    } catch (_) {}
  }

  @override
  void dispose() {
    _vinController.dispose();
    _makeController.dispose();
    _modelController.dispose();
    _yearController.dispose();
    _engineController.dispose();
    _transmissionController.dispose();
    super.dispose();
  }

  void _nextStep() {
    if (_step < 3) {
      setState(() => _step++);
    }
  }

  void _prevStep() {
    if (_step > 0) {
      setState(() => _step--);
    }
  }

  Future<void> _runCheck() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      // Create precheck
      _createdPrecheck = await _api.createPrecheck(
        vehicleId: widget.vehicleId ?? '',
        jurisdiction: _jurisdiction,
        modifications: _modifications,
        vin: _vinController.text.isNotEmpty ? _vinController.text : null,
        make: _makeController.text.isNotEmpty ? _makeController.text : null,
        model: _modelController.text.isNotEmpty ? _modelController.text : null,
        year: int.tryParse(_yearController.text),
        bodyType: _bodyType,
        engine: _engineController.text.isNotEmpty ? _engineController.text : null,
        transmission: _transmissionController.text.isNotEmpty ? _transmissionController.text : null,
      );

      // Complete the precheck (runs compliance engine)
      _createdPrecheck = await _api.completePrecheck(_createdPrecheck!.id);

      // Fetch results
      _results = await _api.getComplianceResults(_createdPrecheck!.id);

      if (mounted) setState(() => _step = 3);
    } catch (e) {
      if (mounted) setState(() => _error = e is ApiException ? e.message : '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _addModification() {
    final nameCtrl = TextEditingController();
    String cat = 'other';
    final brandCtrl = TextEditingController();
    final notesCtrl = TextEditingController();

    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Add Modification'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: nameCtrl,
              decoration: const InputDecoration(
                labelText: 'Modification Name *',
                hintText: 'e.g., K&N Cold Air Intake',
              ),
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              value: cat,
              decoration: const InputDecoration(labelText: 'Category'),
              items: _modCategories.map((c) =>
                DropdownMenuItem(value: c, child: Text(c[0].toUpperCase() + c.substring(1)))
              ).toList(),
              onChanged: (v) => cat = v ?? 'other',
            ),
            const SizedBox(height: 12),
            TextField(
              controller: brandCtrl,
              decoration: const InputDecoration(
                labelText: 'Brand',
                hintText: 'e.g., K&N',
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: notesCtrl,
              decoration: const InputDecoration(
                labelText: 'Notes',
                hintText: 'Any additional details',
              ),
              maxLines: 2,
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              if (nameCtrl.text.trim().isEmpty) return;
              setState(() {
                _modifications.add(ModificationSelection(
                  name: nameCtrl.text.trim(),
                  category: cat,
                  brand: brandCtrl.text.trim().isNotEmpty ? brandCtrl.text.trim() : null,
                  notes: notesCtrl.text.trim().isNotEmpty ? notesCtrl.text.trim() : null,
                ));
              });
              Navigator.of(ctx).pop();
            },
            child: const Text('Add'),
          ),
        ],
      ),
    );
  }

  void _removeModification(int index) {
    setState(() => _modifications.removeAt(index));
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: const Text('VASS Pre-Check'),
        leading: _step > 0
            ? IconButton(
                icon: const Icon(Icons.arrow_back),
                onPressed: _busy ? null : _prevStep,
              )
            : null,
      ),
      body: _busy
          ? const Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  CircularProgressIndicator(),
                  SizedBox(height: 16),
                  Text('Running compliance checks...'),
                ],
              ),
            )
          : Column(
              children: [
                // Step indicator
                _StepIndicator(currentStep: _step, totalSteps: 4),
                if (_error != null)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    color: scheme.errorContainer,
                    child: Row(
                      children: [
                        Icon(Icons.error_outline, color: scheme.onErrorContainer, size: 18),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            _error!,
                            style: TextStyle(color: scheme.onErrorContainer, fontSize: 13),
                          ),
                        ),
                      ],
                    ),
                  ),
                Expanded(
                  child: SingleChildScrollView(
                    padding: const EdgeInsets.all(16),
                    child: _buildStepContent(),
                  ),
                ),
                // Bottom navigation
                SafeArea(
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Row(
                      children: [
                        if (_step > 0)
                          Expanded(
                            child: OutlinedButton(
                              onPressed: _prevStep,
                              child: const Text('Back'),
                            ),
                          ),
                        if (_step > 0) const SizedBox(width: 12),
                        Expanded(
                          child: _step == 2
                              ? FilledButton(
                                  onPressed: _modifications.isNotEmpty ? _runCheck : null,
                                  child: const Text('Run Compliance Check'),
                                )
                              : _step == 3
                                  ? FilledButton(
                                      onPressed: () {
                                        if (_createdPrecheck != null) {
                                          Navigator.of(context).push(
                                            MaterialPageRoute(
                                              builder: (_) => ComplianceResultsScreen(
                                                precheckId: _createdPrecheck!.id,
                                              ),
                                            ),
                                          );
                                        }
                                      },
                                      child: const Text('View Full Results'),
                                    )
                                  : FilledButton(
                                      onPressed: _nextStep,
                                      child: const Text('Next'),
                                    ),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
    );
  }

  Widget _buildStepContent() {
    switch (_step) {
      case 0:
        return _VehicleInfoStep(
          vinController: _vinController,
          makeController: _makeController,
          modelController: _modelController,
          yearController: _yearController,
          bodyType: _bodyType,
          bodyTypes: _bodyTypes,
          engineController: _engineController,
          transmissionController: _transmissionController,
          jurisdiction: _jurisdiction,
          onJurisdictionChanged: (j) => setState(() => _jurisdiction = j),
          onBodyTypeChanged: (t) => setState(() => _bodyType = t),
        );
      case 1:
        return _VehicleInfoStep(
          vinController: _vinController,
          makeController: _makeController,
          modelController: _modelController,
          yearController: _yearController,
          bodyType: _bodyType,
          bodyTypes: _bodyTypes,
          engineController: _engineController,
          transmissionController: _transmissionController,
          jurisdiction: _jurisdiction,
          onJurisdictionChanged: (j) => setState(() => _jurisdiction = j),
          onBodyTypeChanged: (t) => setState(() => _bodyType = t),
        );
      case 2:
        return _ModificationChecklistStep(
          modifications: _modifications,
          onAdd: _addModification,
          onRemove: _removeModification,
        );
      case 3:
        return _ResultsSummaryStep(
          precheck: _createdPrecheck,
          results: _results,
          jurisdiction: _jurisdiction,
          onGeneratePack: _createdPrecheck != null
              ? () async {
                  try {
                    final pack = await _api.generatePack(_createdPrecheck!.id);
                    if (mounted) {
                      Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => PdfViewerScreen(
                            packId: pack.id,
                            title: pack.filename,
                          ),
                        ),
                      );
                    }
                  } catch (e) {
                    if (mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(content: Text('Failed to generate pack: $e')),
                      );
                    }
                  }
                }
              : null,
        );
      default:
        return const SizedBox.shrink();
    }
  }
}

// ---------------------------------------------------------------------------
// Step Indicator
// ---------------------------------------------------------------------------

class _StepIndicator extends StatelessWidget {
  const _StepIndicator({required this.currentStep, required this.totalSteps});
  final int currentStep;
  final int totalSteps;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final labels = ['Vehicle', 'Details', 'Mods', 'Results'];
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Row(
        children: List.generate(totalSteps, (i) {
          final isActive = i <= currentStep;
          final isCurrent = i == currentStep;
          return Expanded(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Row(
                  children: [
                    Container(
                      width: 28,
                      height: 28,
                      decoration: BoxDecoration(
                        color: isActive
                            ? scheme.primary
                            : scheme.surfaceContainerHighest,
                        shape: BoxShape.circle,
                        border: isCurrent
                            ? Border.all(color: scheme.primary, width: 2)
                            : null,
                      ),
                      child: Center(
                        child: i < currentStep
                            ? Icon(Icons.check, size: 16, color: scheme.onPrimary)
                            : Text(
                                '${i + 1}',
                                style: TextStyle(
                                  color: isActive
                                      ? scheme.onPrimary
                                      : scheme.onSurfaceVariant,
                                  fontSize: 12,
                                  fontWeight: FontWeight.w700,
                                ),
                              ),
                      ),
                    ),
                    if (i < totalSteps - 1)
                      Expanded(
                        child: Container(
                          height: 2,
                          color: i < currentStep
                              ? scheme.primary
                              : scheme.surfaceContainerHighest,
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  labels[i],
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: isCurrent ? FontWeight.w700 : FontWeight.w500,
                    color: isActive
                        ? scheme.onSurface
                        : scheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          );
        }),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Step 1 & 2: Vehicle Info
// ---------------------------------------------------------------------------

class _VehicleInfoStep extends StatelessWidget {
  const _VehicleInfoStep({
    required this.vinController,
    required this.makeController,
    required this.modelController,
    required this.yearController,
    required this.bodyType,
    required this.bodyTypes,
    required this.engineController,
    required this.transmissionController,
    required this.jurisdiction,
    required this.onJurisdictionChanged,
    required this.onBodyTypeChanged,
  });

  final TextEditingController vinController, makeController, modelController;
  final TextEditingController yearController, engineController, transmissionController;
  final String bodyType;
  final List<String> bodyTypes;
  final VassJurisdiction jurisdiction;
  final ValueChanged<VassJurisdiction> onJurisdictionChanged;
  final ValueChanged<String> onBodyTypeChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Vehicle Information',
          style: Theme.of(context).textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 4),
        Text(
          'Enter your vehicle details or scan the VIN.',
          style: TextStyle(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
            fontSize: 13,
          ),
        ),
        const SizedBox(height: 16),
        TextField(
          controller: vinController,
          decoration: InputDecoration(
            labelText: 'VIN',
            hintText: '17-character Vehicle Identification Number',
            prefixIcon: const Icon(Icons.qr_code_scanner, size: 20),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
          maxLength: 17,
          textCapitalization: TextCapitalization.characters,
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: makeController,
                decoration: InputDecoration(
                  labelText: 'Make *',
                  hintText: 'e.g., Honda',
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                textCapitalization: TextCapitalization.words,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: TextField(
                controller: modelController,
                decoration: InputDecoration(
                  labelText: 'Model *',
                  hintText: 'e.g., CBR500R',
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                textCapitalization: TextCapitalization.words,
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: yearController,
                decoration: InputDecoration(
                  labelText: 'Year',
                  hintText: 'e.g., 2023',
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                keyboardType: TextInputType.number,
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: DropdownButtonFormField<String>(
                value: bodyType,
                decoration: InputDecoration(
                  labelText: 'Body Type',
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                items: bodyTypes.map((t) =>
                  DropdownMenuItem(value: t, child: Text(t))
                ).toList(),
                onChanged: (v) {
                  if (v != null) onBodyTypeChanged(v);
                },
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        TextField(
          controller: engineController,
          decoration: InputDecoration(
            labelText: 'Engine',
            hintText: 'e.g., 471cc Parallel Twin',
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: transmissionController,
          decoration: InputDecoration(
            labelText: 'Transmission',
            hintText: 'e.g., 6-Speed Manual',
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
            ),
          ),
        ),
        const SizedBox(height: 20),
        Text(
          'Jurisdiction',
          style: Theme.of(context).textTheme.titleSmall?.copyWith(
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: VassJurisdiction.values.map((j) {
            final isSelected = j == jurisdiction;
            return ChoiceChip(
              label: Text(j.name),
              selected: isSelected,
              onSelected: (_) => onJurisdictionChanged(j),
              avatar: isSelected ? Icon(Icons.check_circle, size: 16) : null,
            );
          }).toList(),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Step 3: Modification Checklist
// ---------------------------------------------------------------------------

class _ModificationChecklistStep extends StatelessWidget {
  const _ModificationChecklistStep({
    required this.modifications,
    required this.onAdd,
    required this.onRemove,
  });

  final List<ModificationSelection> modifications;
  final VoidCallback onAdd;
  final ValueChanged<int> onRemove;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                'Modifications',
                style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            FilledButton.tonalIcon(
              onPressed: onAdd,
              icon: const Icon(Icons.add, size: 18),
              label: const Text('Add'),
            ),
          ],
        ),
        const SizedBox(height: 4),
        Text(
          'Add all vehicle modifications that may affect road legality.',
          style: TextStyle(
            color: Theme.of(context).colorScheme.onSurfaceVariant,
            fontSize: 13,
          ),
        ),
        const SizedBox(height: 16),
        if (modifications.isEmpty)
          Center(
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: Column(
                children: [
                  Icon(Icons.build_circle_outlined,
                      size: 48,
                      color: Theme.of(context).colorScheme.onSurfaceVariant),
                  const SizedBox(height: 12),
                  Text(
                    'No modifications added yet.\nTap "Add" to check a modification.',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ),
            ),
          )
        else
          ...List.generate(modifications.length, (i) {
            final mod = modifications[i];
            return Card(
              margin: const EdgeInsets.only(bottom: 8),
              child: ListTile(
                leading: CircleAvatar(
                  backgroundColor: Theme.of(context).colorScheme.primaryContainer,
                  child: Icon(Icons.tune, size: 18),
                ),
                title: Text(mod.name, style: const TextStyle(fontWeight: FontWeight.w600)),
                subtitle: Text(
                  '${mod.category[0].toUpperCase()}${mod.category.substring(1)}'
                  '${mod.brand != null ? ' · ${mod.brand}' : ''}',
                ),
                trailing: IconButton(
                  icon: const Icon(Icons.delete_outline, size: 20),
                  onPressed: () => onRemove(i),
                ),
              ),
            );
          }),
        if (modifications.isNotEmpty) ...[
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Theme.of(context).colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              children: [
                Icon(Icons.info_outline, size: 18, color: Theme.of(context).colorScheme.primary),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '${modifications.length} modification(s) will be checked against '
                    'Australian Design Rules and VSB standards.',
                    style: const TextStyle(fontSize: 13),
                  ),
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Step 4: Results Summary
// ---------------------------------------------------------------------------

class _ResultsSummaryStep extends StatelessWidget {
  const _ResultsSummaryStep({
    required this.precheck,
    required this.results,
    required this.jurisdiction,
    required this.onGeneratePack,
  });

  final VassPrecheck? precheck;
  final List<VassComplianceResult> results;
  final VassJurisdiction jurisdiction;
  final VoidCallback? onGeneratePack;

  @override
  Widget build(BuildContext context) {
    if (results.isEmpty) {
      return const Center(
        child: Text('No results yet. Run the compliance check first.'),
      );
    }

    final passed = results.where((r) => r.status == VassComplianceStatus.pass).length;
    final failed = results.where((r) => r.status == VassComplianceStatus.fail).length;
    final conditional = results.where((r) => r.status == VassComplianceStatus.conditional).length;
    final total = results.length;
    final score = total > 0 ? (passed / total * 100).round() : 0;

    final scoreColor = score >= 80
        ? Colors.green
        : score >= 50
            ? Colors.orange
            : Colors.red;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Score card
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: scoreColor.withValues(alpha: 0.1),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: scoreColor.withValues(alpha: 0.3)),
          ),
          child: Row(
            children: [
              SizedBox(
                width: 80,
                height: 80,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    SizedBox(
                      width: 80,
                      height: 80,
                      child: CircularProgressIndicator(
                        value: score / 100,
                        strokeWidth: 8,
                        backgroundColor: scoreColor.withValues(alpha: 0.15),
                        valueColor: AlwaysStoppedAnimation(scoreColor),
                      ),
                    ),
                    Text(
                      '$score%',
                      style: TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.w800,
                        color: scoreColor,
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
                      'Compliance Score',
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      '$total modification(s) checked in ${jurisdiction.name}',
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                        fontSize: 13,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 16),
        // Summary chips
        Row(
          children: [
            _ResultChip(label: 'Pass', count: passed, color: Colors.green),
            const SizedBox(width: 8),
            _ResultChip(label: 'Conditional', count: conditional, color: Colors.orange),
            const SizedBox(width: 8),
            _ResultChip(label: 'Fail', count: failed, color: Colors.red),
          ],
        ),
        const SizedBox(height: 20),
        Text(
          'Results',
          style: Theme.of(context).textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 8),
        ...results.map((r) => _ComplianceResultCard(result: r)),
        const SizedBox(height: 16),
        // Generate PDF pack
        if (onGeneratePack != null)
          SizedBox(
            width: double.infinity,
            child: FilledButton.tonalIcon(
              onPressed: onGeneratePack,
              icon: const Icon(Icons.picture_as_pdf, size: 20),
              label: const Text('Generate Compliance Pack (PDF)'),
            ),
          ),
      ],
    );
  }
}

class _ResultChip extends StatelessWidget {
  const _ResultChip({required this.label, required this.count, required this.color});
  final String label;
  final int count;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 6),
          Text(
            '$count $label',
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: color,
            ),
          ),
        ],
      ),
    );
  }
}

class _ComplianceResultCard extends StatelessWidget {
  const _ComplianceResultCard({required this.result});
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
      margin: const EdgeInsets.only(bottom: 8),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(_statusIcon(result.status), color: color, size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    result.modificationName,
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    result.status.displayName,
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.w700,
                      color: color,
                    ),
                  ),
                ),
              ],
            ),
            if (refs.isNotEmpty) ...[
              const SizedBox(height: 8),
              Wrap(
                spacing: 6,
                runSpacing: 4,
                children: refs.map((ref) => Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.surfaceContainerHighest,
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    ref,
                    style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600),
                  ),
                )).toList(),
              ),
            ],
            if (result.notes != null && result.notes!.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                result.notes!,
                style: TextStyle(
                  fontSize: 13,
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                  height: 1.4,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}