/// Share-scope picker (AUT-332 contract): field-level opt-ins, default minimal
/// = photos + specs + mods. Mirrors the server `ShareScopeIn` schema.
library;

import 'package:flutter/material.dart';

class ShareScopeState {
  ShareScopeState({
    this.allowPhotos = true,
    this.allowSpecs = true,
    this.allowMods = true,
    this.allowOdometer = false,
    this.allowNotes = false,
  });

  bool allowPhotos;
  bool allowSpecs;
  bool allowMods;
  bool allowOdometer;
  bool allowNotes;
}

class ShareScopePicker extends StatelessWidget {
  const ShareScopePicker({super.key, required this.scope, this.onChanged});

  final ShareScopeState scope;
  final VoidCallback? onChanged;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Share', style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 4),
        Text('Choose what this build shares.',
            style: TextStyle(fontSize: 12, color: Theme.of(context).colorScheme.onSurfaceVariant)),
        const SizedBox(height: 8),
        CheckboxListTile(
          value: scope.allowPhotos,
          onChanged: (v) {
            scope.allowPhotos = v ?? true;
            onChanged?.call();
          },
          dense: true,
          controlAffinity: ListTileControlAffinity.leading,
          contentPadding: EdgeInsets.zero,
          title: const Text('Photos'),
        ),
        CheckboxListTile(
          value: scope.allowSpecs,
          onChanged: (v) {
            scope.allowSpecs = v ?? true;
            onChanged?.call();
          },
          dense: true,
          controlAffinity: ListTileControlAffinity.leading,
          contentPadding: EdgeInsets.zero,
          title: const Text('Vehicle specs (make, model, engine…)'),
        ),
        CheckboxListTile(
          value: scope.allowMods,
          onChanged: (v) {
            scope.allowMods = v ?? true;
            onChanged?.call();
          },
          dense: true,
          controlAffinity: ListTileControlAffinity.leading,
          contentPadding: EdgeInsets.zero,
          title: const Text('Mod list'),
        ),
        CheckboxListTile(
          value: scope.allowOdometer,
          onChanged: (v) {
            scope.allowOdometer = v ?? true;
            onChanged?.call();
          },
          dense: true,
          controlAffinity: ListTileControlAffinity.leading,
          contentPadding: EdgeInsets.zero,
          title: const Text('Odometer'),
        ),
        CheckboxListTile(
          value: scope.allowNotes,
          onChanged: (v) {
            scope.allowNotes = v ?? true;
            onChanged?.call();
          },
          dense: true,
          controlAffinity: ListTileControlAffinity.leading,
          contentPadding: EdgeInsets.zero,
          title: const Text('Notes'),
        ),
      ],
    );
  }
}
