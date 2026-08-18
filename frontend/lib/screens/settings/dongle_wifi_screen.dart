/// Dongle WiFi upload settings + BLE provisioning (AUT-936).
///
/// Screen sections:
/// 1. Toggle the WiFi auto-upload feature (persisted locally).
/// 2. SSID + password entry for the dongle's home WiFi.
/// 3. Link the dongle to this account: reuse an existing device or create a
///    new one (the create response carries a ONE-TIME api_key — shown once
///    with a copy button, never recoverable afterwards).
/// 4. Push the provisioning payload over BLE to the AutoBrain-Tripper and
///    read the firmware ack.
/// 5. Status: last successful upload time (from GET /devices) + a local
///    queue hint.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/config.dart';
import '../../core/models.dart';
import '../../services/dongle/dongle_api.dart';
import '../../services/dongle/dongle_ble.dart';
import '../../services/dongle/dongle_provisioning.dart';
import '../../services/dongle/dongle_settings.dart';

class DongleWifiScreen extends StatefulWidget {
  const DongleWifiScreen({super.key});

  @override
  State<DongleWifiScreen> createState() => _DongleWifiScreenState();
}

class _DongleWifiScreenState extends State<DongleWifiScreen> {
  DongleConfig _config = const DongleConfig(enabled: false, ssid: '', pass: '');
  final _ssid = TextEditingController();
  final _pass = TextEditingController();
  List<DongleDevice> _devices = const [];
  List<Vehicle> _vehicles = const [];
  DongleDevice? _linked;
  bool _loading = true;
  bool _busy = false;
  String? _status;
  String? _loadError;
  String? _confirmedDeviceId;

  bool get _enabled => _config.enabled;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _ssid.dispose();
    _pass.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final api = context.read<AuthState>().api;
    final cfg = await DongleSettings.load();
    setState(() {
      _config = cfg;
      _ssid.text = cfg.ssid;
      _pass.text = cfg.pass;
    });
    try {
      final devices = await DongleApi(api).list();
      List<Vehicle> vehicles = const [];
      try {
        final data = await api.get('/vehicles') as List;
        vehicles = data
            .map((e) => Vehicle.fromJson(e as Map<String, dynamic>))
            .toList();
      } catch (_) {}
      if (!mounted) return;
      setState(() {
        _devices = devices;
        _vehicles = vehicles;
        _linked = _resolveLinked(devices, cfg);
        _loadError = null;
      });
    } catch (_) {
      // Distinct from "no dongle linked": the list/vehicle fetch itself failed
      // (offline, auth, server) and we cannot say anything about linkage yet
      // (AUT-968 F4).
      if (mounted) setState(() => _loadError = 'Could not reach the server.');
    }
    if (mounted) setState(() => _loading = false);
  }

  /// Reuses the saved device only when it still exists in the current
  /// account's list; otherwise returns null so the user re-links. Never falls
  /// back to a different device — that would push the previous account's key
  /// into a device the user never chose (AUT-963 F1).
  DongleDevice? _resolveLinked(List<DongleDevice> devices, DongleConfig cfg) {
    if (devices.isEmpty) return null;
    for (final d in devices) {
      if (d.id == cfg.deviceId) return d;
    }
    return null;
  }

  String? _apiUrlForSelfHosted() =>
      AppConfig.apiBase == AppConfig.hostedApi ? null : AppConfig.apiBase;

  Future<void> _setEnabled(bool value) async {
    await DongleSettings.save(
      enabled: value,
      ssid: _ssid.text.trim(),
      pass: _pass.text,
      deviceId: _config.deviceId,
      deviceName: _config.deviceName,
      vehicleId: _config.vehicleId,
      apiKey: _config.apiKey,
    );
    setState(() {
      _config = DongleConfig(
        enabled: value,
        ssid: _ssid.text.trim(),
        pass: _pass.text,
        deviceId: _config.deviceId,
        deviceName: _config.deviceName,
        vehicleId: _config.vehicleId,
        apiKey: _config.apiKey,
      );
    });
  }

  Future<void> _createDevice() async {
    if (_busy) return;
    final api = context.read<AuthState>().api;
    final name = TextEditingController(text: 'AutoBrain-Tripper');
    String? vehicleId;
    setState(() => _busy = true);
    final choice = await showDialog<({String name, String? vehicleId})>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialog) => AlertDialog(
          title: const Text('Link dongle to account'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: name,
                autofocus: true,
                decoration: const InputDecoration(
                  labelText: 'Dongle name',
                  hintText: 'AutoBrain-Tripper',
                ),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String?>(
                initialValue: vehicleId,
                decoration: const InputDecoration(labelText: 'Vehicle (optional)'),
                items: [
                  const DropdownMenuItem<String?>(
                    value: null,
                    child: Text('No vehicle'),
                  ),
                  for (final v in _vehicles)
                    DropdownMenuItem<String?>(
                      value: v.id,
                      child: Text(v.dropdownLabel, overflow: TextOverflow.ellipsis),
                    ),
                ],
                onChanged: (v) => setDialog(() => vehicleId = v),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(ctx)
                  .pop((name: name.text.trim(), vehicleId: vehicleId)),
              child: const Text('Create'),
            ),
          ],
        ),
      ),
    );
    setState(() => _busy = false);
    if (choice == null) return;
    try {
      final device = await DongleApi(api).create(
        name: choice.name.isEmpty ? 'AutoBrain-Tripper' : choice.name,
        vehicleId: choice.vehicleId,
      );
      if (!mounted) return;
      await _showOneTimeKey(device);
      setState(() {
        _devices = [device, ..._devices];
        _linked = device;
      });
      await DongleSettings.save(
        enabled: _enabled,
        ssid: _ssid.text.trim(),
        pass: _pass.text,
        deviceId: device.id,
        deviceName: device.name,
        vehicleId: device.vehicleId,
        apiKey: device.oneTimeApiKey,
      );
      _config = await DongleSettings.load();
    } catch (e) {
      if (mounted) {
        setState(() => _status = 'Could not create dongle: $e');
      }
    }
  }

  Future<void> _showOneTimeKey(DongleDevice device) async {
    final key = device.oneTimeApiKey;
    if (key == null) return;
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Your dongle API key'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('This key is shown ONCE and stored only as a hash on '
                'the server — it cannot be recovered later.'),
            const SizedBox(height: 12),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Theme.of(ctx).colorScheme.surfaceContainerHighest,
                borderRadius: BorderRadius.circular(8),
              ),
              child: SelectableText(key, style: const TextStyle(fontFamily: 'monospace')),
            ),
            const SizedBox(height: 8),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                onPressed: () async {
                  await Clipboard.setData(ClipboardData(text: key));
                  if (ctx.mounted) {
                    ScaffoldMessenger.of(ctx).showSnackBar(
                      const SnackBar(content: Text('API key copied')),
                    );
                  }
                },
                icon: const Icon(Icons.copy),
                label: const Text('Copy'),
              ),
            ),
          ],
        ),
        actions: [
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('I saved it'),
          ),
        ],
      ),
    );
  }

  Future<void> _push() async {
    final cfg = _config;
    final ssid = _ssid.text.trim();
    final pass = _pass.text;
    final inputError = validateWifiInput(ssid: ssid, pass: pass);
    if (inputError != null) {
      setState(() => _status = inputError);
      return;
    }
    if (cfg.deviceId == null || cfg.apiKey == null) {
      setState(() => _status = 'Link the dongle to your account first.');
      return;
    }
    if (_linked == null || _linked!.id != cfg.deviceId) {
      setState(() => _status = 'Re-link the dongle to your account first.');
      return;
    }
    final payload = buildProvisioningPayload(
      ssid: ssid,
      pass: pass,
      deviceId: cfg.deviceId!,
      apiKey: cfg.apiKey!,
      apiUrl: _apiUrlForSelfHosted(),
    );
    await DongleSettings.save(
      enabled: true,
      ssid: ssid,
      pass: pass,
      deviceId: cfg.deviceId,
      deviceName: cfg.deviceName,
      vehicleId: cfg.vehicleId,
      apiKey: cfg.apiKey,
    );
    setState(() {
      _config = DongleConfig(
        enabled: true,
        ssid: ssid,
        pass: pass,
        deviceId: cfg.deviceId,
        deviceName: cfg.deviceName,
        vehicleId: cfg.vehicleId,
        apiKey: cfg.apiKey,
      );
      _busy = true;
      _status = 'Looking for the dongle…';
    });
    try {
      final candidates = await DongleBle.scan();
      if (!mounted) return;
      final choice = await _confirmDongle(candidates);
      if (choice == null) {
        if (!mounted) return;
        setState(() => _status = 'Provisioning cancelled.');
        return;
      }
      setState(() {
        _confirmedDeviceId = choice.deviceId;
        _status = 'Provisioning ${choice.name}…';
      });
      final ack =
          await DongleBle.provision(payload, deviceId: _confirmedDeviceId!);
      if (!mounted) return;
      setState(() {
        _status = ack.trim() == 'ok'
            ? 'Dongle provisioned — it will upload trips over WiFi automatically.'
            : 'Dongle reply: $ack';
      });
    } catch (e) {
      if (mounted) setState(() => _status = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Security gate (AUT-966): never write provisioning credentials until the
  /// user picks the exact dongle from every discovered match. Returns the
  /// confirmed peripheral, or null when the user cancels. Each option shows
  /// the advertised name + MAC/remoteId.
  Future<DonglePeripheral?> _confirmDongle(
      List<DonglePeripheral> candidates) {
    return showDialog<DonglePeripheral>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Confirm dongle'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Pick the dongle to receive your WiFi credentials '
                  'and API key. Only the device you pick is provisioned.'),
              const SizedBox(height: 12),
              for (final d in candidates)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.settings_input_antenna),
                  title: Text(d.name),
                  subtitle: Text(d.deviceId),
                  onTap: () => Navigator.of(ctx).pop(d),
                ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text('Cancel'),
          ),
        ],
      ),
    );
  }

  String? get _lastSeenLabel {
    final lastSeen = _linked?.lastSeenAt;
    if (lastSeen == null) return null;
    return DateFormat('d MMM yyyy, h:mm a').format(lastSeen.toLocal());
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Dongle WiFi upload')),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(16),
              children: [
                Card(
                  child: SwitchListTile(
                    secondary: const Icon(Icons.wifi),
                    title: const Text('WiFi auto-upload'),
                    subtitle: const Text('The AutoBrain-Tripper dongle uploads '
                        'completed trips to your logbook over WiFi automatically.'),
                    value: _enabled,
                    onChanged: _busy ? null : _setEnabled,
                  ),
                ),
                if (_enabled) ...[
                  const SizedBox(height: 8),
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Home WiFi network',
                              style: Theme.of(context).textTheme.titleSmall),
                          const SizedBox(height: 12),
                          TextField(
                            controller: _ssid,
                            enabled: !_busy,
                            // Firmware buffers ssid[33] and truncates silently
                            // (AUT-968 F3); cap at the 802.11 limit here.
                            maxLength: 32,
                            decoration: const InputDecoration(
                              labelText: 'WiFi name (SSID)',
                              prefixIcon: Icon(Icons.wifi),
                            ),
                          ),
                          const SizedBox(height: 8),
                          TextField(
                            controller: _pass,
                            enabled: !_busy,
                            obscureText: true,
                            // WPA2 passphrase cap (firmware pass[64]).
                            maxLength: 63,
                            decoration: const InputDecoration(
                              labelText: 'WiFi password',
                              prefixIcon: Icon(Icons.password),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('Dongle account link',
                              style: Theme.of(context).textTheme.titleSmall),
                          const SizedBox(height: 8),
                          if (_linked == null)
                            Text(_loadError ?? 'No dongle linked yet. Create one to '
                                'receive its one-time API key.')
                          else ...[
                            ListTile(
                              contentPadding: EdgeInsets.zero,
                              leading: const Icon(Icons.settings_input_antenna),
                              title: Text(_linked!.name),
                              subtitle: Text('Last upload: '
                                  '${_lastSeenLabel ?? 'never'}'),
                              trailing: const Icon(Icons.chevron_right),
                            ),
                          ],
                          const SizedBox(height: 8),
                          Row(
                            children: [
                              FilledButton.tonalIcon(
                                onPressed: _busy ? null : _createDevice,
                                icon: const Icon(Icons.add_link),
                                label: Text(
                                    _linked == null ? 'Link dongle' : 'Add another dongle'),
                              ),
                              if (_linked != null) ...[
                                const SizedBox(width: 8),
                                FilledButton.tonalIcon(
                                  onPressed: _busy ? null : _push,
                                  icon: const Icon(Icons.bluetooth),
                                  label: const Text('Push credentials'),
                                ),
                              ],
                            ],
                          ),
                          const SizedBox(height: 8),
                          const Text(
                              'Trips queue on the dongle and upload over WiFi — '
                              'no phone needed on the road.',
                              style: TextStyle(fontSize: 12)),
                        ],
                      ),
                    ),
                  ),
                ],
                if (_status != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: _busy
                        ? const Row(children: [
                            SizedBox(
                                width: 16,
                                height: 16,
                                child: CircularProgressIndicator(strokeWidth: 2)),
                            SizedBox(width: 8),
                            Expanded(child: Text('Looking for the dongle…')),
                          ])
                        : Text(_status!),
                  ),
              ],
            ),
    );
  }
}
