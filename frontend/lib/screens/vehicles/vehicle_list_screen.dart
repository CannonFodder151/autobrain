import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../../core/connectivity_service.dart';
import '../../core/models.dart';
import '../../widgets/rego_status_badge.dart';
import '../../widgets/responsive.dart';
import '../../widgets/stale_hint.dart';
import 'add_vehicle_screen.dart';
import 'edit_vehicle_screen.dart';
import 'share_vehicle_screen.dart';

class VehicleListScreen extends StatefulWidget {
  const VehicleListScreen({super.key});

  @override
  State<VehicleListScreen> createState() => _VehicleListScreenState();
}

class _VehicleListScreenState extends State<VehicleListScreen> {
  List<Vehicle> _vehicles = const [];
  List<Map<String, dynamic>> _invites = const [];
  bool _loading = true;
  bool _stale = false;
  String? _busyInvite;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    // Cache-first: render immediately from cache.
    final cached = await api.getCachedDecoded('/vehicles', null);
    if (cached != null) {
      _vehicles = (cached as List)
          .map((e) => Vehicle.fromJson(e as Map<String, dynamic>))
          .toList();
      _stale = true;
      if (!mounted) return;
      setState(() => _loading = false);
    }
    if (!mounted) return;
    // Background refresh if online.
    if (!ConnectivityService.instance.isOnline) return;
    try {
      final data = await api.get('/vehicles') as List;
      _vehicles = data
          .map((e) => Vehicle.fromJson(e as Map<String, dynamic>))
          .toList();
      _stale = false;
    } catch (_) {
      if (_vehicles.isEmpty) _stale = true;
    }
    try {
      final invites = await api.get('/vehicle-shares') as List;
      _invites = invites.map((e) => e as Map<String, dynamic>).toList();
    } catch (_) {}
    if (mounted) setState(() {});
  }

  Future<void> _delete(Vehicle v) async {
    final api = context.read<AuthState>().api;
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Delete vehicle?'),
        content: Text('${v.nickname} and all its data will be removed.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (ok == true) {
      await api.delete('/vehicles/${v.id}');
      _load();
    }
  }

  Future<void> _edit(Vehicle v) async {
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => EditVehicleScreen(vehicle: v)),
    );
    _load();
  }

  Future<void> _share(Vehicle v) async {
    await Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => ShareVehicleScreen(vehicle: v)),
    );
    _load();
  }

  Future<void> _respond(String shareId, String action) async {
    final api = context.read<AuthState>().api;
    setState(() => _busyInvite = shareId);
    try {
      await api.post('/vehicle-shares/$shareId/$action');
      await _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    } finally {
      if (mounted) setState(() => _busyInvite = null);
    }
  }

  Future<void> _removeShared(Vehicle v) async {
    final share = _invites.firstWhere(
      (i) => i['vehicle_id'] == v.id,
      orElse: () => const {},
    );
    final shareId = share['id'] as String?;
    if (shareId == null) return;
    final api = context.read<AuthState>().api;
    try {
      await api.delete('/vehicle-shares/$shareId');
      _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    final isDemo = auth.isDemo;
    final isPremium = auth.premium;
    final pending = _invites.where((i) => i['status'] == 'pending').toList();
    return Scaffold(
      appBar: AppBar(title: const Text('Vehicles')),
      floatingActionButton: isDemo
          ? null
          : FloatingActionButton.extended(
              onPressed: () async {
                await Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const AddVehicleScreen()),
                );
                _load();
              },
              icon: const Icon(Icons.add),
              label: const Text('Add vehicle'),
            ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  StaleHint(
                    isStale: _stale,
                    isOffline: !ConnectivityService.instance.isOnline,
                  ),
                  Center(
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 700),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          if (pending.isNotEmpty) ...[
                            Text('Vehicle invites',
                                style: Theme.of(context).textTheme.titleMedium),
                            const SizedBox(height: 8),
                            for (final i in pending) _InviteCard(
                              invite: i,
                              busy: _busyInvite == i['id'],
                              onAccept: () => _respond(i['id'] as String, 'accept'),
                              onDeny: () => _respond(i['id'] as String, 'deny'),
                            ),
                            const SizedBox(height: 16),
                          ],
                          for (final v in _vehicles)
                            Card(
                              child: Padding(
                                padding: const EdgeInsets.symmetric(
                                    horizontal: 12, vertical: 8),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    InkWell(
                                      onTap: v.isShared ? null : () => _edit(v),
                                      child: Row(
                                        children: [
                                          Icon(v.isShared
                                              ? Icons.group
                                              : Icons.directions_car),
                                          const SizedBox(width: 12),
                                          Expanded(
                                            child: Column(
                                              crossAxisAlignment: CrossAxisAlignment.start,
                                              children: [
                                                Text(v.dropdownLabel,
                                                    style: Theme.of(context)
                                                        .textTheme
                                                        .titleMedium),
                                                Text(
                                                  '${v.make ?? ''} ${v.model ?? ''} ${v.year ?? ''}'
                                                  '${v.bodyType != null ? ' · ${v.bodyType}' : ''}'
                                                  '${v.colour != null ? ' · ${v.colour}' : ''}'
                                                  '${v.rego != null ? ' · ${v.rego}' : ''}'
                                                      .trim(),
                                                  style: Theme.of(context)
                                                      .textTheme
                                                      .bodySmall,
                                                ),
                                              ],
                                            ),
                                          ),
                                          if (v.isPrimary)
                                            const Padding(
                                              padding: EdgeInsets.only(right: 4),
                                              child: Icon(Icons.star,
                                                  color: Colors.amber),
                                            ),
                                          PopupMenuButton<String>(
                                            onSelected: (action) {
                                              if (action == 'edit') _edit(v);
                                              if (action == 'share') _share(v);
                                              if (action == 'delete') _delete(v);
                                              if (action == 'remove') _removeShared(v);
                                            },
                                            itemBuilder: (_) => v.isShared
                                                ? const [
                                                    PopupMenuItem(
                                                        value: 'remove',
                                                        child: Text('Remove access')),
                                                  ]
                                                : const [
                                                    PopupMenuItem(
                                                        value: 'edit',
                                                        child: Text('Edit details')),
                                                    PopupMenuItem(
                                                        value: 'share',
                                                        child: Text('Share')),
                                                    PopupMenuItem(
                                                        value: 'delete',
                                                        child: Text('Delete')),
                                                  ],
                                          ),
                                        ],
                                      ),
                                    ),
                                    if (v.hasRegoData)
                                      Padding(
                                        padding: const EdgeInsets.only(
                                            left: 36, top: 4, bottom: 4),
                                        child: RegoStatusBadge(
                                          vehicle: v,
                                          premium: isPremium,
                                        ),
                                      ),
                                  ],
                                ),
                              ),
                            ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
    );
  }
}

class _InviteCard extends StatelessWidget {
  const _InviteCard({
    required this.invite,
    required this.busy,
    required this.onAccept,
    required this.onDeny,
  });

  final Map<String, dynamic> invite;
  final bool busy;
  final VoidCallback onAccept;
  final VoidCallback onDeny;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: const Icon(Icons.person_add_alt_1),
        title: Text(invite['vehicle_nickname'] as String? ?? 'A vehicle'),
        subtitle:
            Text('${invite['owner_name'] as String? ?? ''} wants to share '
                'a vehicle with you'),
        trailing: busy
            ? const SizedBox(
                height: 20,
                width: 20,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextButton(
                    onPressed: onDeny,
                    child: const Text('Deny'),
                  ),
                  FilledButton(
                    onPressed: onAccept,
                    child: const Text('Accept'),
                  ),
                ],
              ),
      ),
    );
  }
}
