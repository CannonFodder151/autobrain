/// Social compose — pick vehicle + photos (max 6), set share scope, publish.
library;

import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/models.dart';
import '../models.dart';
import '../social_api.dart';
import '../widgets/premium_gate.dart';
import '../widgets/share_scope_picker.dart';

class SocialComposeScreen extends StatefulWidget {
  const SocialComposeScreen({super.key});

  @override
  State<SocialComposeScreen> createState() => _SocialComposeScreenState();
}

class _SocialComposeScreenState extends State<SocialComposeScreen> {
  List<Vehicle> _vehicles = const [];
  Vehicle? _vehicle;
  final _caption = TextEditingController();
  final _scope = ShareScopeState();
  final List<({String name, String mime, Uint8List bytes})> _picked = [];
  bool _loading = true;
  bool _publishing = false;

  @override
  void initState() {
    super.initState();
    _loadVehicles();
  }

  @override
  void dispose() {
    _caption.dispose();
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

  Future<void> _pickPhotos() async {
    if (_picked.length >= 6) {
      _toast('Maximum 6 photos.');
      return;
    }
    final files = await ImagePicker().pickMultiImage(
      maxWidth: 2048,
      imageQuality: 82,
    );
    if (files.isEmpty) return;
    final picked = <({String name, String mime, Uint8List bytes})>[];
    for (final f in files) {
      if (picked.length + _picked.length >= 6) break;
      picked.add((
        name: f.name,
        mime: f.mimeType ?? 'image/jpeg',
        bytes: await f.readAsBytes(),
      ));
    }
    if (mounted) setState(() => _picked.addAll(picked));
  }

  Future<void> _publish() async {
    if (_vehicle == null) {
      _toast('Select a vehicle first.');
      return;
    }
    setState(() => _publishing = true);
    final api = SocialApi(context.read<AuthState>().api);
    try {
      final photoIds = <String>[];
      for (final p in _picked) {
        final uploaded = await api.uploadPhoto(p.bytes, p.name, p.mime);
        photoIds.add(uploaded.id);
      }
      await api.createPost(
        vehicleId: _vehicle!.id,
        caption: _caption.text.trim().isEmpty ? null : _caption.text.trim(),
        photoIds: photoIds,
        allowPhotos: _scope.allowPhotos,
        allowSpecs: _scope.allowSpecs,
        allowMods: _scope.allowMods,
        allowOdometer: _scope.allowOdometer,
        allowNotes: _scope.allowNotes,
      );
      if (mounted) {
        Navigator.of(context).pop(true);
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Build shared to the feed.')));
      }
    } on ApiException catch (e) {
      _toast(e.message);
    } catch (e) {
      _toast('Could not publish: $e');
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
        title: const Text('Share a build'),
        actions: [
          TextButton(
            onPressed: _publishing ? null : _publish,
            child: _publishing
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Publish'),
          ),
        ],
      ),
      body: auth.freeAccount
          ? const PremiumGate()
          : _loading
              ? const Center(child: CircularProgressIndicator())
              : ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    _vehiclePicker(),
                    const SizedBox(height: 16),
                    TextField(
                      controller: _caption,
                      maxLines: 3,
                      maxLength: 1000,
                      decoration: const InputDecoration(
                        labelText: 'Caption',
                        border: OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: 12),
                    _photoPicker(),
                    const SizedBox(height: 16),
                    ShareScopePicker(scope: _scope),
                  ],
                ),
    );
  }

  Widget _vehiclePicker() {
    return DropdownButtonFormField<Vehicle>(
      value: _vehicle,
      isExpanded: true,
      decoration: const InputDecoration(
        labelText: 'Vehicle',
        border: OutlineInputBorder(),
      ),
      items: [
        for (final v in _vehicles)
          DropdownMenuItem(value: v, child: Text(v.dropdownLabel)),
      ],
      onChanged: (v) => setState(() => _vehicle = v),
    );
  }

  Widget _photoPicker() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Photos (up to 6)', style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 8),
        if (_picked.isEmpty)
          OutlinedButton.icon(
            onPressed: _pickPhotos,
            icon: const Icon(Icons.add_photo_alternate_outlined),
            label: const Text('Pick photos'),
          )
        else
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (var i = 0; i < _picked.length; i++)
                Stack(
                  children: [
                    ClipRRect(
                      borderRadius: BorderRadius.circular(8),
                      child: Image.memory(_picked[i].bytes,
                          width: 84, height: 84, fit: BoxFit.cover,
                          errorBuilder: (_, __, ___) => const SizedBox(
                              width: 84, height: 84, child: Icon(Icons.image))),
                    ),
                    Positioned(
                      top: 2,
                      right: 2,
                      child: InkWell(
                        onTap: () => setState(() => _picked.removeAt(i)),
                        child: const CircleAvatar(
                          radius: 10,
                          backgroundColor: Colors.black54,
                          child: Icon(Icons.close, size: 14, color: Colors.white),
                        ),
                      ),
                    ),
                  ],
                ),
              if (_picked.length < 6)
                InkWell(
                  onTap: _pickPhotos,
                  borderRadius: BorderRadius.circular(8),
                  child: Container(
                    width: 84,
                    height: 84,
                    decoration: BoxDecoration(
                      border: Border.all(color: Theme.of(context).colorScheme.outline),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Icon(Icons.add),
                  ),
                ),
            ],
          ),
      ],
    );
  }
}
