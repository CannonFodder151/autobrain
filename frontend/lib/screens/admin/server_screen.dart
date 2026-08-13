import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/auth_state.dart';
import '../../core/download.dart';

/// Admin-only server page: version, full backup, restore, and the
/// machine-to-machine admin API key note.
class ServerScreen extends StatefulWidget {
  const ServerScreen({super.key});

  @override
  State<ServerScreen> createState() => _ServerScreenState();
}

class _ServerScreenState extends State<ServerScreen> {
  Map<String, dynamic>? _version;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final data = await context
          .read<AuthState>()
          .api
          .get('/admin/version') as Map<String, dynamic>;
      if (mounted) setState(() => _version = data);
    } catch (_) {}
  }

  Future<void> _backup() async {
    setState(() => _busy = true);
    try {
      final bytes = await context.read<AuthState>().api.export('/admin/backup');
      await downloadBytes('autobrain-backup.json', bytes);
    } catch (e) {
      _snack('Backup failed: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _restore() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Restore full backup?'),
        content: const Text(
          'WARNING: This wipes ALL current data (all users, vehicles, history) '
          'and replaces it with the backup file. This cannot be undone. '
          'Make a fresh backup first.',
          style: TextStyle(color: Colors.red),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Restore'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['json'],
    );
    if (result == null || result.files.isEmpty) return;
    final picked = result.files.single;
    final List<int> bytes;
    if (picked.bytes != null) {
      bytes = picked.bytes!;
    } else if (picked.path != null) {
      bytes = await readLocalFile(picked.path!);
    } else {
      return;
    }
    setState(() => _busy = true);
    try {
      await context.read<AuthState>().api.upload(
            '/admin/restore',
            bytes,
            picked.name,
            'application/json',
          );
      _snack('Restore complete.');
    } catch (e) {
      _snack('Restore failed: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _snack(String msg) {
    if (mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(msg)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final v = _version;
    return Scaffold(
      appBar: AppBar(title: const Text('Server')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Server version',
                      style: Theme.of(context).textTheme.titleMedium),
                  const SizedBox(height: 8),
                  if (v == null)
                    const Text('Loading…')
                  else
                    Text(
                      'v${v['version'] ?? '?'}',
                      style: Theme.of(context)
                          .textTheme
                          .headlineSmall
                          ?.copyWith(fontWeight: FontWeight.bold),
                    ),
                  const SizedBox(height: 8),
                  Text(
                    'Repository: CannonFodder151/autobrain',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 12),
          Card(
            child: ListTile(
              leading: const Icon(Icons.history),
              title: const Text('Changelog'),
              subtitle: const Text(
                  'What changed in each release — view CHANGELOG.md on GitHub'),
              trailing: const Icon(Icons.open_in_new),
              onTap: () => _openUrl(
                  'https://github.com/CannonFodder151/autobrain/blob/main/CHANGELOG.md'),
            ),
          ),
          const SizedBox(height: 16),
          Text('Backup & restore',
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          const Text(
              'A daily scheduled backup is stored in MinIO automatically. '
              'Download a fresh snapshot before any restore.'),
          const SizedBox(height: 12),
          FilledButton.tonalIcon(
            onPressed: _busy ? null : _backup,
            icon: const Icon(Icons.download),
            label: const Text('Download full backup'),
          ),
          const SizedBox(height: 8),
          OutlinedButton.icon(
            onPressed: _busy ? null : _restore,
            icon: const Icon(Icons.upload_file),
            label: const Text('Restore from backup'),
          ),
          const SizedBox(height: 24),
          const Card(
            child: Padding(
              padding: EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Admin API (machine-to-machine)',
                      style: TextStyle(fontWeight: FontWeight.bold)),
                  SizedBox(height: 8),
                  Text(
                    'An API key (ADMIN_API_KEY) enables external systems to create '
                    'users, set permissions (role, vehicle quota, free/paid account, '
                    'OBD access), list, disable and delete users via '
                    '/api/v1/admin-api/* with the X-Admin-API-Key header. '
                    'See .env.example.',
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _openUrl(String url) async {
    final ok = await launchUrl(Uri.parse(url),
        mode: LaunchMode.externalApplication);
    if (!ok && mounted) _snack('Could not open link');
  }
}
