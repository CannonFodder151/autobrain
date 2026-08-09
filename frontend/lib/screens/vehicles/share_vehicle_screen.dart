import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/models.dart';

class ShareVehicleScreen extends StatefulWidget {
  const ShareVehicleScreen({super.key, required this.vehicle});

  final Vehicle vehicle;

  @override
  State<ShareVehicleScreen> createState() => _ShareVehicleScreenState();
}

class _ShareVehicleScreenState extends State<ShareVehicleScreen> {
  final _email = TextEditingController();
  bool _busy = false;
  bool _loading = true;
  String? _error;
  List<Map<String, dynamic>> _shares = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _email.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final rows = await api.get('/vehicles/${widget.vehicle.id}/shares');
      setState(() {
        _shares = (rows as List)
            .map((r) => r as Map<String, dynamic>)
            .toList();
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _loading = false;
        _error = '$e';
      });
    }
  }

  Future<void> _share() async {
    final email = _email.text.trim();
    if (email.isEmpty) return;
    final api = context.read<AuthState>().api;
    setState(() => _busy = true);
    try {
      await api.post('/vehicles/${widget.vehicle.id}/shares', {'email': email});
      _email.clear();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Invite sent')),
        );
      }
      await _load();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$e')));
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Share ${widget.vehicle.nickname}')),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              controller: _email,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(
                labelText: 'Email of the person to share with',
              ),
              onSubmitted: (_) => _share(),
            ),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: _busy ? null : _share,
              child: const Text('Share vehicle'),
            ),
            const SizedBox(height: 20),
            Text('Shared with', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            if (_loading)
              const Center(child: CircularProgressIndicator())
            else if (_error != null)
              Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error))
            else if (_shares.isEmpty)
              const Text('Not shared with anyone yet.')
            else
              Expanded(
                child: ListView.builder(
                  itemCount: _shares.length,
                  itemBuilder: (context, i) {
                    final s = _shares[i];
                    final pending = s['status'] == 'pending';
                    return ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: const Icon(Icons.person),
                      title: Text(
                        (s['invitee_display_name'] as String?) ?? 'Unknown',
                      ),
                      subtitle: Text((s['invitee_email'] as String?) ?? ''),
                      trailing: Text(
                        pending ? 'Pending' : 'Accepted',
                        style: TextStyle(
                          color: pending
                              ? Theme.of(context).colorScheme.tertiary
                              : Colors.green,
                        ),
                      ),
                    );
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }
}
