/// Issue compose — title + body + optional vehicle context snapshot (AUT-627).
/// Tags are detected deterministically server-side from title/body/vehicle.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/models.dart';
import '../social_api.dart';
import '../widgets/premium_gate.dart';

class IssueComposeScreen extends StatefulWidget {
  const IssueComposeScreen({super.key});

  @override
  State<IssueComposeScreen> createState() => _IssueComposeScreenState();
}

class _IssueComposeScreenState extends State<IssueComposeScreen> {
  List<Vehicle> _vehicles = const [];
  Vehicle? _vehicle;
  final _title = TextEditingController();
  final _body = TextEditingController();
  bool _loading = true;
  bool _publishing = false;

  @override
  void initState() {
    super.initState();
    _loadVehicles();
  }

  @override
  void dispose() {
    _title.dispose();
    _body.dispose();
    super.dispose();
  }

  Future<void> _loadVehicles() async {
    final api = context.read<AuthState>().api;
    try {
      final data = await api.get('/vehicles') as List;
      final vehicles = data
          .map((e) => Vehicle.fromJson(e as Map<String, dynamic>))
          .toList();
      setState(() {
        _vehicles = vehicles;
        _vehicle = Vehicle.resolveSelection(vehicles, null);
      });
    } catch (_) {}
    setState(() => _loading = false);
  }

  Future<void> _publish() async {
    final title = _title.text.trim();
    final body = _body.text.trim();
    if (title.isEmpty || body.isEmpty) {
      _toast('Add a title and describe your problem.');
      return;
    }
    setState(() => _publishing = true);
    final api = SocialApi(context.read<AuthState>().api);
    try {
      await api.createIssue(
        title: title,
        body: body,
        vehicleId: _vehicle?.id,
      );
      if (mounted) {
        Navigator.of(context).pop(true);
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Issue posted to the blog.')));
      }
    } on ApiException catch (e) {
      _toast(e.message);
    } catch (e) {
      _toast('Could not post: $e');
    }
    setState(() => _publishing = false);
  }

  void _toast(String message) {
    if (mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Ask for help'),
        actions: [
          TextButton(
            onPressed: _publishing ? null : _publish,
            child: _publishing
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Post'),
          ),
        ],
      ),
      body: auth.freeAccount
          ? const PremiumGate(
              lockedReason:
                  'The Issues Blog is a premium member feature — get help from real owners.')
          : _loading
              ? const Center(child: CircularProgressIndicator())
              : ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    TextField(
                      controller: _title,
                      maxLength: 150,
                      textCapitalization: TextCapitalization.sentences,
                      decoration: const InputDecoration(
                        labelText: 'Title',
                        hintText: 'e.g. Engine won\'t start when hot',
                        border: OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: _body,
                      maxLines: 8,
                      maxLength: 4000,
                      textCapitalization: TextCapitalization.sentences,
                      decoration: const InputDecoration(
                        labelText: 'Describe the problem',
                        hintText: 'What\'s happening? When did it start? Any warning lights?',
                        border: OutlineInputBorder(),
                        alignLabelWithHint: true,
                      ),
                    ),
                    const SizedBox(height: 16),
                    _vehiclePicker(),
                    const SizedBox(height: 8),
                    Text(
                      'Tags are added automatically based on your description.',
                      style: TextStyle(
                          fontSize: 12,
                          color: Theme.of(context).colorScheme.onSurfaceVariant),
                    ),
                  ],
                ),
    );
  }

  Widget _vehiclePicker() {
    if (_vehicles.isEmpty) {
      return const SizedBox.shrink();
    }
    return DropdownButtonFormField<Vehicle>(
      initialValue: _vehicle,
      isExpanded: true,
      decoration: const InputDecoration(
        labelText: 'Vehicle (optional context)',
        border: OutlineInputBorder(),
      ),
      items: [
        for (final v in _vehicles)
          DropdownMenuItem(value: v, child: Text(v.dropdownLabel)),
      ],
      onChanged: (v) => setState(() => _vehicle = v),
    );
  }
}
