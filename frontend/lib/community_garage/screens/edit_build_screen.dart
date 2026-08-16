/// Edit build (AUT-675) — rename, reorder/add/remove photos, tweak what the
/// build shares. Replaces the old caption-only dialog on My Builds.
library;

import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../models.dart';
import '../social_api.dart';
import '../widgets/share_scope_picker.dart';

class _PhotoEntry {
  _PhotoEntry({this.id, this.url, this.bytes, this.name, this.mime});
  String? id;
  String? url;
  Uint8List? bytes;
  String? name;
  String? mime;
}

class EditBuildScreen extends StatefulWidget {
  const EditBuildScreen({super.key, required this.build});

  final SocialBuild build;

  @override
  State<EditBuildScreen> createState() => _EditBuildScreenState();
}

class _EditBuildScreenState extends State<EditBuildScreen> {
  static const _maxPhotos = 6;

  final _title = TextEditingController();
  final _caption = TextEditingController();
  final List<_PhotoEntry> _photos = [];
  late final ShareScopeState _scope;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _title.text = widget.build.title ?? '';
    _caption.text = widget.build.caption ?? '';
    for (var i = 0; i < widget.build.photos.length; i++) {
      _photos.add(_PhotoEntry(
        id: i < widget.build.photoIds.length ? widget.build.photoIds[i] : null,
        url: widget.build.photos[i],
      ));
    }
    final s = widget.build.shareScope;
    _scope = ShareScopeState(
      allowPhotos: s['allow_photos'] ?? true,
      allowSpecs: s['allow_specs'] ?? true,
      allowMods: s['allow_mods'] ?? true,
      allowOdometer: s['allow_odometer'] ?? false,
      allowNotes: s['allow_notes'] ?? false,
    );
  }

  @override
  void dispose() {
    _title.dispose();
    _caption.dispose();
    super.dispose();
  }

  Future<void> _pickPhotos() async {
    if (_photos.length >= _maxPhotos) {
      _toast('Maximum $_maxPhotos photos.');
      return;
    }
    final files = await ImagePicker().pickMultiImage(
      maxWidth: 2048,
      imageQuality: 82,
    );
    if (files.isEmpty) return;
    try {
      for (final f in files) {
        if (_photos.length >= _maxPhotos) break;
        _photos.add(_PhotoEntry(
          bytes: await f.readAsBytes(),
          name: f.name,
          mime: (f.mimeType?.trim().isNotEmpty ?? false) ? f.mimeType! : 'image/jpeg',
        ));
      }
    } catch (_) {
      _toast('Could not read that photo. Try a different file.');
      return;
    }
    if (mounted) setState(() {});
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    final api = SocialApi(context.read<AuthState>().api);
    try {
      final newIds = <String>[];
      for (final p in _photos) {
        if (p.id == null) {
          final uploaded =
              await api.uploadPhoto(p.bytes!, p.name ?? 'photo.jpg', p.mime!);
          newIds.add(uploaded.id);
        }
      }
      final photoIds = <String>[];
      for (final p in _photos) {
        photoIds.add(p.id ?? newIds.removeAt(0));
      }
      final updated = await api.updatePost(
        widget.build.id,
        title: _title.text.trim().isEmpty ? null : _title.text.trim(),
        caption: _caption.text.trim(), // "" clears, null would mean unchanged
        photoIds: photoIds,
        allowPhotos: _scope.allowPhotos,
        allowSpecs: _scope.allowSpecs,
        allowMods: _scope.allowMods,
        allowOdometer: _scope.allowOdometer,
        allowNotes: _scope.allowNotes,
      );
      if (mounted) {
        Navigator.of(context).pop(updated);
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Build updated.')));
      }
    } on ApiException catch (e) {
      _toast(e.message);
    } catch (e) {
      _toast('Could not save: $e');
    }
    setState(() => _saving = false);
  }

  void _toast(String message) {
    if (mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Edit build'),
        actions: [
          TextButton(
            onPressed: _saving ? null : _save,
            child: _saving
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Save'),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: _title,
            maxLength: 200,
            decoration: const InputDecoration(
              labelText: 'Project name',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
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
          _photoEditor(),
          const SizedBox(height: 16),
          ShareScopePicker(scope: _scope, onChanged: () => setState(() {})),
        ],
      ),
    );
  }

  Widget _photoEditor() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Photos (up to $_maxPhotos — drag to reorder)',
            style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 8),
        if (_photos.isEmpty)
          OutlinedButton.icon(
            onPressed: _pickPhotos,
            icon: const Icon(Icons.add_photo_alternate_outlined),
            label: const Text('Pick photos'),
          )
        else
          SizedBox(
            height: 96,
            child: ReorderableListView.builder(
              scrollDirection: Axis.horizontal,
              buildDefaultDragHandles: false,
              itemCount: _photos.length + (_photos.length < _maxPhotos ? 1 : 0),
              onReorderItem: (oldIndex, newIndex) {
                setState(() {
                  final item = _photos.removeAt(oldIndex);
                  _photos.insert(newIndex, item);
                });
              },
              itemBuilder: (context, index) {
                if (index >= _photos.length) {
                  return Padding(
                    key: const ValueKey('add'),
                    padding: const EdgeInsets.only(right: 8),
                    child: InkWell(
                      onTap: _pickPhotos,
                      borderRadius: BorderRadius.circular(8),
                      child: Container(
                        width: 96,
                        height: 96,
                        decoration: BoxDecoration(
                          border: Border.all(
                              color: Theme.of(context).colorScheme.outline),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Icon(Icons.add),
                      ),
                    ),
                  );
                }
                final photo = _photos[index];
                return Padding(
                  key: ValueKey(index),
                  padding: const EdgeInsets.only(right: 8),
                  child: Stack(
                    children: [
                      ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: photo.bytes != null
                            ? Image.memory(photo.bytes!, width: 96, height: 96,
                                fit: BoxFit.cover)
                            : Image.network(photo.url!,
                                width: 96, height: 96, fit: BoxFit.cover,
                                errorBuilder: (_, __, ___) => Container(
                                    width: 96,
                                    height: 96,
                                    color: Colors.black12,
                                    child: const Icon(Icons.image))),
                      ),
                      Positioned(
                        top: 2,
                        right: 2,
                        child: InkWell(
                          onTap: () => setState(() => _photos.removeAt(index)),
                          child: const CircleAvatar(
                            radius: 10,
                            backgroundColor: Colors.black54,
                            child: Icon(Icons.close,
                                size: 14, color: Colors.white),
                          ),
                        ),
                      ),
                      Positioned(
                        bottom: 2,
                        left: 2,
                        child: ReorderableDragStartListener(
                          index: index,
                          child: const CircleAvatar(
                            radius: 10,
                            backgroundColor: Colors.black54,
                            child: Icon(Icons.drag_handle,
                                size: 14, color: Colors.white),
                          ),
                        ),
                      ),
                    ],
                  ),
                );
              },
            ),
          ),
      ],
    );
  }
}
