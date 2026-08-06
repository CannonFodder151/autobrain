import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/download.dart';
import 'server_screen.dart';

class AdminScreen extends StatefulWidget {
  const AdminScreen({super.key});

  @override
  State<AdminScreen> createState() => _AdminScreenState();
}

class _AdminScreenState extends State<AdminScreen> {
  List<Map<String, dynamic>> _users = const [];
  bool _loading = true;
  String _query = '';
  Map<String, dynamic>? _version;

  @override
  void initState() {
    super.initState();
    _load();
    _loadVersion();
  }

  Future<void> _loadVersion() async {
    try {
      final data = await context
          .read<AuthState>()
          .api
          .get('/admin/version') as Map<String, dynamic>;
      if (mounted) setState(() => _version = data);
    } catch (_) {}
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    setState(() => _loading = true);
    try {
      final data = await api.get('/admin/users?q=${Uri.encodeQueryComponent(_query)}') as List;
      _users = data.cast<Map<String, dynamic>>();
    } catch (_) {}
    setState(() => _loading = false);
  }

  Future<void> _create() async {
    final formKey = GlobalKey<FormState>();
    final email = TextEditingController();
    final name = TextEditingController();
    final password = TextEditingController();
    final maxVehicles = TextEditingController(text: '1');
    String role = 'user';
    var sendInvite = false;
    var freeAccount = false;
    var obdEnabled = false;
    final api = context.read<AuthState>().api;
    final created = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          title: const Text('Create user'),
          content: Form(
            key: formKey,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextFormField(
                  controller: email,
                  decoration: const InputDecoration(labelText: 'Email'),
                  validator: (v) => v == null || !v.contains('@') ? 'Valid email' : null,
                ),
                TextFormField(
                  controller: name,
                  decoration: const InputDecoration(labelText: 'Display name'),
                  validator: (v) => v == null || v.isEmpty ? 'Required' : null,
                ),
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Email user an invite'),
                  subtitle: const Text('No password needed — user sets it from the email link'),
                  value: sendInvite,
                  onChanged: (v) => setDialogState(() => sendInvite = v ?? false),
                ),
                if (!sendInvite)
                  TextFormField(
                    controller: password,
                    decoration: const InputDecoration(labelText: 'Password'),
                    obscureText: true,
                    validator: (v) => v == null || v.length < 8 ? 'Min 8 chars' : null,
                  ),
                DropdownButtonFormField<String>(
                  value: role,
                  items: const [
                    DropdownMenuItem(value: 'user', child: Text('User')),
                    DropdownMenuItem(value: 'admin', child: Text('Admin')),
                  ],
                  onChanged: (v) => role = v ?? 'user',
                ),
                TextFormField(
                  controller: maxVehicles,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                    labelText: 'Max vehicles',
                    helperText: 'Vehicle limit for this user (default 1)',
                  ),
                ),
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Free account'),
                  subtitle: const Text('Disables AI and rego lookup'),
                  value: freeAccount,
                  onChanged: (v) => setDialogState(() => freeAccount = v ?? false),
                ),
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Grant OBD access'),
                  value: obdEnabled,
                  onChanged: (v) => setDialogState(() => obdEnabled = v ?? false),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
            FilledButton(
              onPressed: () {
                if (formKey.currentState!.validate()) Navigator.pop(ctx, true);
              },
              child: const Text('Create'),
            ),
          ],
        ),
      ),
    );
    if (created == true) {
      try {
        await api.post('/admin/users', {
          'email': email.text,
          'display_name': name.text,
          if (sendInvite) ...{'send_invite': true} else 'password': password.text,
          'role': role,
          'max_vehicles': int.tryParse(maxVehicles.text) ?? 1,
          'free_account': freeAccount,
          'obd_enabled': obdEnabled,
        });
        _load();
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
        }
      }
    }
  }

  Future<void> _update(Map<String, dynamic> u, Map<String, dynamic> changes) async {
    final api = context.read<AuthState>().api;
    try {
      await api.patch('/admin/users/${u['id']}', changes);
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  Future<void> _setLimit(Map<String, dynamic> u) async {
    final controller = TextEditingController(
        text: (u['max_vehicles'] ?? 1).toString());
    final saved = await showDialog<int>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Vehicle limit'),
        content: TextField(
          controller: controller,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(
            labelText: 'Max vehicles',
            helperText: 'How many vehicles this user may add',
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
            onPressed: () {
              final v = int.tryParse(controller.text);
              if (v != null && v >= 1) Navigator.pop(ctx, v);
            },
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (saved != null) _update(u, {'max_vehicles': saved});
  }

  Future<void> _reUpgrade(Map<String, dynamic> u) async {
    // Sponsored (free_account=false, no Stripe sub) => revoke; else grant.
    final enable = u['free_account'] == true;
    final api = context.read<AuthState>().api;
    try {
      await api.post('/admin/users/${u['id']}/re-upgrade?enabled=$enable');
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  Future<void> _delete(Map<String, dynamic> u) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete user?'),
        content: Text('${u['email']} will lose access immediately.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Delete', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
    if (ok == true) {
      final api = context.read<AuthState>().api;
      await api.delete('/admin/users/${u['id']}');
      _load();
    }
  }

  Future<void> _backupUser(Map<String, dynamic> u) async {
    final api = context.read<AuthState>().api;
    try {
      final bytes = await api.export('/admin/users/${u['id']}/backup');
      await downloadBytes('autobrain-user.json', bytes);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Backup failed: $e')));
      }
    }
  }

  Future<void> _restoreUser(Map<String, dynamic> u) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('Restore ${u['email']}?'),
        content: const Text(
            'Replaces this user\'s vehicles and records with the profile file. '
            'The account itself stays.'),
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
    final api = context.read<AuthState>().api;
    try {
      await api.upload(
          '/admin/users/${u['id']}/restore', bytes, picked.name, 'application/json');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('User profile restored.')));
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('Restore failed: $e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('User administration'),
        actions: [
          IconButton(
            tooltip: 'Server: version, backup & restore',
            icon: const Icon(Icons.dns),
            onPressed: () async {
              await Navigator.of(context).push(
                MaterialPageRoute(builder: (_) => const ServerScreen()),
              );
              _loadVersion();
            },
          ),
          IconButton(onPressed: _create, icon: const Icon(Icons.person_add_alt)),
        ],
      ),
      body: Column(
        children: [
          if (_version != null) _VersionBanner(version: _version!),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
            child: TextField(
              onChanged: (v) {
                _query = v;
                _load();
              },
              decoration: const InputDecoration(
                labelText: 'Search users',
                prefixIcon: Icon(Icons.search),
              ),
            ),
          ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _users.isEmpty
                    ? const Center(child: Text('No users'))
                    : ListView.builder(
                        padding: const EdgeInsets.all(16),
                        itemCount: _users.length,
                        itemBuilder: (context, i) {
                          final u = _users[i];
                          final isAdmin = u['role'] == 'admin';
                          final active = u['is_active'] == true;
                          final free = u['free_account'] == true;
                          final obd = u['obd_enabled'] == true;
                          final licenseOn = context.read<AuthState>().licenseEnabled;
                          return Card(
                            child: ListTile(
                              leading: CircleAvatar(
                                child: Icon(isAdmin ? Icons.shield : Icons.person),
                              ),
                              title: Text(u['display_name']),
                              subtitle: Text(
                                '${u['email']} · ${u['max_vehicles'] ?? 1} vehicle limit'
                                '${free ? ' · FREE' : ''}'
                                '${obd ? ' · OBD' : ''}'
                                '${u['mfa_enabled'] == true ? ' · MFA ✓' : ''}',
                              ),
                              trailing: PopupMenuButton<String>(
                                onSelected: (v) {
                                  switch (v) {
                                    case 'toggle_active':
                                      _update(u, {'is_active': !active});
                                    case 'toggle_role':
                                      _update(u, {'role': isAdmin ? 'user' : 'admin'});
                                    case 'toggle_free':
                                      _update(u, {'free_account': !free});
                                    case 'reup':
                                      _reUpgrade(u);
                                    case 'toggle_obd':
                                      _update(u, {'obd_enabled': !obd});
                                    case 'limit':
                                      _setLimit(u);
                                    case 'backup':
                                      _backupUser(u);
                                    case 'restore':
                                      _restoreUser(u);
                                    case 'delete':
                                      _delete(u);
                                  }
                                },
                                itemBuilder: (_) => [
                                  PopupMenuItem(
                                      value: 'limit',
                                      child: const Text('Set vehicle limit')),
                                  PopupMenuItem(
                                      value: 'backup',
                                      child: const Text('Backup user')),
                                  PopupMenuItem(
                                      value: 'restore',
                                      child: const Text('Restore user')),
                                  if (licenseOn) ...[
                                    PopupMenuItem(
                                        value: 'toggle_free',
                                        child: Text(free
                                            ? 'Upgrade to paid account'
                                            : 'Set as free account')),
                                    PopupMenuItem(
                                        value: 'reup',
                                        child: Text(free
                                            ? r'Re-upgrade ($19/mo benefits)'
                                            : 'Remove re-upgrade')),
                                  ],
                                  PopupMenuItem(
                                      value: 'toggle_obd',
                                      child: Text(obd
                                          ? 'Revoke OBD access'
                                          : 'Grant OBD access')),
                                  PopupMenuItem(
                                      value: 'toggle_active',
                                      child: Text(active ? 'Disable account' : 'Enable account')),
                                  PopupMenuItem(
                                      value: 'toggle_role',
                                      child: Text(isAdmin ? 'Demote to user' : 'Promote to admin')),
                                  const PopupMenuDivider(),
                                  const PopupMenuItem(value: 'delete', child: Text('Delete')),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
          ),
        ],
      ),
    );
  }
}

class _VersionBanner extends StatelessWidget {
  const _VersionBanner({required this.version});
  final Map<String, dynamic> version;

  @override
  Widget build(BuildContext context) {
    final current = version['version']?.toString() ?? '?';
    final latest = version['latest_version']?.toString();
    final upToDate = version['up_to_date'];
    final reachable = version['reachable'] == true;
    final repoVersion = version['repo_version']?.toString();
    String statusText;
    Color statusColor;
    if (!reachable) {
      statusText = "GitHub unreachable — can't check for updates";
      statusColor = Colors.grey;
    } else if (upToDate == null) {
      statusText = 'Checking GitHub…';
      statusColor = Colors.grey;
    } else if (upToDate == true) {
      statusText = repoVersion != null
          ? 'Up to date (v$repoVersion)'
          : 'Up to date (latest: $latest)';
      statusColor = Colors.green;
    } else {
      statusText = repoVersion != null
          ? 'Update available: v$repoVersion'
          : 'Update available: $latest';
      statusColor = Colors.orange;
    }
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      color: statusColor.withValues(alpha: 0.12),
      child: Row(
        children: [
          Icon(Icons.info_outline, color: statusColor, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Server v$current · $statusText',
              style: TextStyle(color: statusColor, fontWeight: FontWeight.w600),
            ),
          ),
        ],
      ),
    );
  }
}
