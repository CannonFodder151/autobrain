import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../../core/config.dart';

/// First-run server selection: pick the hosted subscription or a custom server.
class ServerSetupScreen extends StatefulWidget {
  const ServerSetupScreen({super.key});

  @override
  State<ServerSetupScreen> createState() => _ServerSetupScreenState();
}

class _ServerSetupScreenState extends State<ServerSetupScreen> {
  final _host = TextEditingController();
  final _port = TextEditingController();
  bool _secure = true;
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _host.dispose();
    _port.dispose();
    super.dispose();
  }

  Future<void> _useHosted() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    await AppConfig.setServer(
      apiBaseUrl: AppConfig.hostedApi,
      wsBaseUrl: AppConfig.hostedWs,
    );
    if (!mounted) return;
    context.read<AuthState>().serverChanged();
    setState(() => _busy = false);
  }

  Future<void> _useCustom() async {
    final host = _host.text.trim();
    if (host.isEmpty) {
      setState(() => _error = 'Enter a server host or IP');
      return;
    }
    if (!host.contains('://') && !RegExp(r'^[\w.-]+$').hasMatch(host)) {
      setState(() => _error = 'Enter a hostname or IP (e.g. 192.0.2.1)');
      return;
    }
    final port = int.tryParse(_port.text.trim());
    if (_port.text.trim().isNotEmpty && port == null) {
      setState(() => _error = 'Port must be a number');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    final bases = AppConfig.customBase(host, port, _secure);
    await AppConfig.setServer(apiBaseUrl: bases.api, wsBaseUrl: bases.ws);
    if (!mounted) return;
    context.read<AuthState>().serverChanged();
    setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              scheme.primary,
              scheme.primary.withValues(alpha: 0.75),
              scheme.secondary.withValues(alpha: 0.6),
            ],
          ),
        ),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: Column(
                children: [
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.15),
                          blurRadius: 24,
                          offset: const Offset(0, 8),
                        ),
                      ],
                    ),
                    child: ClipOval(
                      child: Image.asset('assets/logo.png',
                          width: 72, height: 72, fit: BoxFit.cover),
                    ),
                  ),
                  const SizedBox(height: 20),
                  const Text(
                    'Welcome to AutoBrain',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 26,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 6),
                  const Text(
                    'Connect to your AutoBrain instance.',
                    style: TextStyle(color: Colors.white70, fontSize: 15),
                  ),
                  const SizedBox(height: 32),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(24),
                    decoration: BoxDecoration(
                      color: Theme.of(context).colorScheme.surface,
                      borderRadius: BorderRadius.circular(24),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withValues(alpha: 0.18),
                          blurRadius: 32,
                          offset: const Offset(0, 12),
                        ),
                      ],
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        FilledButton.icon(
                          onPressed: _busy ? null : _useHosted,
                          icon: const Icon(Icons.cloud_outlined),
                          label: const Text('Use AutoBrain subscription'),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'Connect to the hosted service at '
                          'hosted.autobrainservice.app',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                              fontSize: 12,
                              color: scheme.onSurfaceVariant),
                        ),
                        const SizedBox(height: 20),
                        Row(
                          children: [
                            const Expanded(child: Divider()),
                            Padding(
                              padding:
                                  const EdgeInsets.symmetric(horizontal: 12),
                              child: Text('OR',
                                  style: TextStyle(
                                      color: scheme.onSurfaceVariant,
                                      fontSize: 12,
                                      fontWeight: FontWeight.w600)),
                            ),
                            const Expanded(child: Divider()),
                          ],
                        ),
                        const SizedBox(height: 20),
                        TextFormField(
                          controller: _host,
                          decoration: const InputDecoration(
                            labelText: 'Custom server',
                            hintText: '192.0.2.1',
                            prefixIcon: Icon(Icons.dns_outlined),
                          ),
                        ),
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Expanded(
                              child: TextFormField(
                                controller: _port,
                                keyboardType: TextInputType.number,
                                inputFormatters: [
                                  FilteringTextInputFormatter.digitsOnly,
                                ],
                                decoration: const InputDecoration(
                                  labelText: 'Port',
                                  hintText: '8000',
                                  prefixIcon: Icon(Icons.numbers),
                                ),
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: SegmentedButton<bool>(
                                segments: const [
                                  ButtonSegment(
                                      value: false,
                                      icon: Icon(Icons.lock_open),
                                      label: Text('http')),
                                  ButtonSegment(
                                      value: true,
                                      icon: Icon(Icons.lock),
                                      label: Text('https')),
                                ],
                                selected: {_secure},
                                onSelectionChanged: (s) =>
                                    setState(() => _secure = s.first),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 16),
                        FilledButton.tonal(
                          onPressed: _busy ? null : _useCustom,
                          child: const Text('Connect to custom server'),
                        ),
                        if (_error != null) ...[
                          const SizedBox(height: 12),
                          Text(_error!,
                              textAlign: TextAlign.center,
                              style: TextStyle(color: Colors.red.shade600)),
                        ],
                      ],
                    ),
                  ),
                  const SizedBox(height: 20),
                  const Text(
                    'You can change this later in Settings.',
                    style: TextStyle(color: Colors.white60, fontSize: 12),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
