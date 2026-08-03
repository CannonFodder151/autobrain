import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';

class AdminScreen extends StatefulWidget {
  const AdminScreen({super.key});

  @override
  State<AdminScreen> createState() => _AdminScreenState();
}

class _AdminScreenState extends State<AdminScreen> {
  List<Map<String, dynamic>> _users = const [];
  bool _loading = true;
  String _query = '';

  @override
  void initState() {
    super.initState();
    _load();
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('User administration'),
        actions: [
          IconButton(onPressed: _create, icon: const Icon(Icons.person_add_alt)),
        ],
      ),
      body: Column(
        children: [
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
                          return Card(
                            child: ListTile(
                              leading: CircleAvatar(
                                child: Icon(isAdmin ? Icons.shield : Icons.person),
                              ),
                              title: Text(u['display_name']),
                              subtitle: Text(
                                '${u['email']} · ${u['max_vehicles'] ?? 1} vehicle limit'
                                '${u['mfa_enabled'] == true ? ' · MFA ✓' : ''}',
                              ),
                              trailing: PopupMenuButton<String>(
                                onSelected: (v) {
                                  switch (v) {
                                    case 'toggle_active':
                                      _update(u, {'is_active': !active});
                                    case 'toggle_role':
                                      _update(u, {'role': isAdmin ? 'user' : 'admin'});
                                    case 'limit':
                                      _setLimit(u);
                                    case 'delete':
                                      _delete(u);
                                  }
                                },
                                itemBuilder: (_) => [
                                  PopupMenuItem(
                                      value: 'limit',
                                      child: const Text('Set vehicle limit')),
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
