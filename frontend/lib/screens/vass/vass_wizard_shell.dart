import 'package:flutter/material.dart';
import 'vehicle_selector_screen.dart';
import 'modification_checklist_screen.dart';

/// Navigation shell connecting VASS wizard steps.
class VassWizardShell extends StatefulWidget {
  const VassWizardShell({super.key});

  @override
  State<VassWizardShell> createState() => _VassWizardShellState();
}

class _VassWizardShellState extends State<VassWizardShell> {
  int _currentStep = 0;

  final List<Widget> _steps = const [
    VassVehicleSelectorScreen(),
    ModificationChecklistScreen(
      vehicleId: 'pending',
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('VASS Pre-Check Wizard'),
      ),
      body: Stepper(
        currentStep: _currentStep,
        onStepContinue: () {
          if (_currentStep < _steps.length - 1) {
            setState(() => _currentStep++);
          }
        },
        onStepCancel: () {
          if (_currentStep > 0) {
            setState(() => _currentStep--);
          }
        },
        controlsBuilder: (context, details) {
          return Padding(
            padding: const EdgeInsets.only(top: 16),
            child: Row(
              children: [
                FilledButton(
                  onPressed: details.onStepContinue,
                  child: Text(
                      _currentStep == _steps.length - 1 ? 'Finish' : 'Next'),
                ),
                const SizedBox(width: 8),
                if (_currentStep > 0)
                  TextButton(
                    onPressed: details.onStepCancel,
                    child: const Text('Back'),
                  ),
              ],
            ),
          );
        },
        steps: [
          Step(
            title: const Text('Vehicle'),
            content: _steps[0],
            isActive: _currentStep >= 0,
            state: _currentStep > 0 ? StepState.complete : StepState.indexed,
          ),
          Step(
            title: const Text('Pre-check'),
            content: _steps[1],
            isActive: _currentStep >= 1,
            state: _currentStep > 1 ? StepState.complete : StepState.indexed,
          ),
        ],
      ),
    );
  }
}
