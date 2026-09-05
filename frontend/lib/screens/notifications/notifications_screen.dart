import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../community_garage/widgets/premium_gate.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key, required this.vehicleId});
  final String vehicleId;

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  Map<String, dynamic>? _pref;
  bool _loading = true;
  bool _saving = false;
  String? _error;
  String? _saved;

  // Editing state
  bool _push = true;
  bool _email = true;
  bool _discord = false;
  int _dueDays = 7;
  int _dueKm = 500;
  int _fuelGapKm = 0;
  int _regoDays = 0;
  final _webhook = TextEditingController();
  final _daysCtrl = TextEditingController();
  final _kmCtrl = TextEditingController();
  final _fuelCtrl = TextEditingController();
  final _regoCtrl = TextEditingController();

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _webhook.dispose();
    _daysCtrl.dispose();
    _kmCtrl.dispose();
    _fuelCtrl.dispose();
    _regoCtrl.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final p = await api.get(
              '/vehicles/${widget.vehicleId}/notifications')
          as Map<String, dynamic>;
      setState(() {
        _pref = p;
        _push = p['push_enabled'] as bool? ?? true;
        _email = p['email_enabled'] as bool? ?? true;
        _discord = p['discord_enabled'] as bool? ?? false;
        _dueDays = (p['service_due_days'] as num?)?.toInt() ?? 7;
        _dueKm = (p['service_due_km'] as num?)?.toInt() ?? 500;
        _fuelGapKm = (p['fuel_gap_km'] as num?)?.toInt() ?? 0;
        _regoDays = (p['rego_expiry_days'] as num?)?.toInt() ?? 0;
        _webhook.text = (p['discord_webhook_url'] as String?) ?? '';
        _daysCtrl.text = '$_dueDays';
        _kmCtrl.text = '$_dueKm';
        _fuelCtrl.text = _fuelGapKm > 0 ? '$_fuelGapKm' : '';
        _regoCtrl.text = _regoDays > 0 ? '$_regoDays' : '';
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _loading = false;
        _error = '$e';
      });
    }
  }

  Future<void> _save() async {
    final api = context.read<AuthState>().api;
    setState(() {
      _saving = true;
      _saved = null;
      _error = null;
    });
    try {
      final body = {
        'push_enabled': _push,
        'email_enabled': _email,
        'discord_enabled': _discord,
        'service_due_days': int.tryParse(_daysCtrl.text) ?? 7,
        'service_due_km': int.tryParse(_kmCtrl.text) ?? 500,
        'fuel_gap_km': int.tryParse(_fuelCtrl.text) ?? 0,
        'rego_expiry_days': int.tryParse(_regoCtrl.text) ?? 0,
        'discord_webhook_url': _webhook.text.trim().isEmpty
            ? null
            : _webhook.text.trim(),
      };
      await api.put('/vehicles/${widget.vehicleId}/notifications', body);
      if (mounted) setState(() => _saved = 'Settings saved');
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Notifications')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                padding: const EdgeInsets.all(16),
                children: [
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Channels',
                              style: Theme.of(context).textTheme.titleMedium),
                          const SizedBox(height: 4),
                          SwitchListTile(
                            contentPadding: EdgeInsets.zero,
                            title: const Text('Push notifications'),
                            subtitle: const Text('In-app / device notifications'),
                            value: _push,
                            onChanged: (v) => setState(() => _push = v),
                          ),
                          SwitchListTile(
                            contentPadding: EdgeInsets.zero,
                            title: const Text('Email'),
                            subtitle: const Text(
                                'Sent from the system email account'),
                            value: _email,
                            onChanged: (v) => setState(() => _email = v),
                          ),
                          SwitchListTile(
                            contentPadding: EdgeInsets.zero,
                            title: const Text('Discord'),
                            subtitle: const Text(
                                'Via your own Discord webhook'),
                            value: _discord,
                            onChanged: (v) => setState(() => _discord = v),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Service due alerts',
                              style: Theme.of(context).textTheme.titleMedium),
                          const SizedBox(height: 4),
                          Text(
                            'Notify when a scheduled service is coming up — '
                            'by days until the due date, by distance to the next '
                            'due km, or both. Evaluated when services and fuel '
                            'data are added.',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                          const SizedBox(height: 14),
                          TextField(
                            controller: _daysCtrl,
                            keyboardType: TextInputType.number,
                            decoration: const InputDecoration(
                              labelText: 'Alert X days before due (0 = off)',
                            ),
                          ),
                          const SizedBox(height: 12),
                          TextField(
                            controller: _kmCtrl,
                            keyboardType: TextInputType.number,
                            decoration: const InputDecoration(
                              labelText: 'Alert X km before due (0 = off)',
                            ),
                          ),
                          const SizedBox(height: 12),
                          TextField(
                            controller: _fuelCtrl,
                            keyboardType: TextInputType.number,
                            decoration: const InputDecoration(
                              labelText:
                                  'Fuel log reminder after X km gap (0 = off)',
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(children: [
                            Text('Rego expiry alert',
                                style: Theme.of(context).textTheme.titleMedium),
                            const SizedBox(width: 8),
                            const _PremiumChip(),
                          ]),
                          const SizedBox(height: 4),
                          Text(
                            'Alert when this vehicle\'s registration is due to '
                            'expire within X days. Evaluated by the daily sweep '
                            'once the rego lookup has populated the expiry date.',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                          const SizedBox(height: 14),
                          if (context.watch<AuthState>().premium)
                            TextField(
                              controller: _regoCtrl,
                              keyboardType: TextInputType.number,
                              decoration: const InputDecoration(
                                labelText:
                                    'Alert X days before rego expires (0 = off)',
                              ),
                            )
                          else
                            const PremiumGate(
                              lockedReason:
                                  'Rego expiry alerts are a premium feature. '
                                  'Upgrade to set a reminder window.',
                            ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Discord webhook',
                              style: Theme.of(context).textTheme.titleMedium),
                          const SizedBox(height: 4),
                          Text(
                            'Paste a Discord webhook URL to receive alerts there. '
                            'You create the webhook in your Discord server — '
                            'AutoBrain never stores or shares your credentials.',
                            style: Theme.of(context).textTheme.bodySmall,
                          ),
                          const SizedBox(height: 12),
                          TextField(
                            controller: _webhook,
                            decoration: const InputDecoration(
                              labelText: 'Discord webhook URL',
                              hintText: 'https://discord.com/api/webhooks/...',
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(_error!,
                        style: TextStyle(color: Colors.red.shade600)),
                  ],
                  if (_saved != null) ...[
                    const SizedBox(height: 12),
                    Text(_saved!,
                        style: TextStyle(color: Colors.green.shade700)),
                  ],
                  const SizedBox(height: 20),
                  FilledButton(
                    onPressed: _saving ? null : _save,
                    child: _saving
                        ? const SizedBox(
                            height: 20,
                            width: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Text('Save notification settings'),
                  ),
                ],
              ),
            ),
    );
  }
}

/// Small "Premium" pill that sits next to gated settings, so the user sees
/// the lock before tapping the field.
class _PremiumChip extends StatelessWidget {
  const _PremiumChip();

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: scheme.primary.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: scheme.primary, width: 1),
      ),
      child: Text('PREMIUM',
          style: TextStyle(
            fontSize: 10,
            fontWeight: FontWeight.w800,
            color: scheme.primary,
            letterSpacing: 0.5,
          )),
    );
  }
}
