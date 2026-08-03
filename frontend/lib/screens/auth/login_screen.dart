import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _code = TextEditingController();
  bool _busy = false;
  bool _mfaStep = false;
  String? _mfaToken;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _code.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final auth = context.read<AuthState>();
    if (_mfaStep) {
      final ok = await auth.verifyMfa(_mfaToken!, _code.text.trim());
      if (!ok && mounted) {
        setState(() {
          _busy = false;
          _error = 'Invalid verification code';
        });
      }
      return;
    }
    final outcome = await auth.login(_email.text, _password.text);
    if (!mounted) return;
    if (outcome == LoginOutcome.mfaRequired) {
      setState(() {
        _mfaStep = true;
        _mfaToken = auth.mfaTokenHint;
        _busy = false;
      });
    } else if (outcome == LoginOutcome.failed) {
      setState(() {
        _busy = false;
        _error = 'Invalid email or password';
      });
    }
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
            colors: [scheme.primary, scheme.primary.withValues(alpha: 0.75), scheme.secondary.withValues(alpha: 0.6)],
          ),
        ),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: Column(
                children: [
                  Container(
                    padding: const EdgeInsets.all(20),
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
                    child: const Icon(Icons.directions_car,
                        size: 44, color: Color(0xFF0B6B6A)),
                  ),
                  const SizedBox(height: 20),
                  const Text(
                    'AutoBrain',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 30,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    _mfaStep ? 'Enter your verification code' : 'Your garage, your data, AI-powered.',
                    style: const TextStyle(color: Colors.white70, fontSize: 15),
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
                    child: Form(
                      key: _formKey,
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          if (!_mfaStep) ...[
                            TextFormField(
                              controller: _email,
                              decoration: const InputDecoration(
                                labelText: 'Email',
                                prefixIcon: Icon(Icons.mail_outline),
                              ),
                              keyboardType: TextInputType.emailAddress,
                              validator: (v) => v == null || !v.contains('@')
                                  ? 'Valid email required'
                                  : null,
                            ),
                            const SizedBox(height: 14),
                            TextFormField(
                              controller: _password,
                              decoration: const InputDecoration(
                                labelText: 'Password',
                                prefixIcon: Icon(Icons.lock_outline),
                              ),
                              obscureText: true,
                              onFieldSubmitted: (_) => _submit(),
                              validator: (v) =>
                                  v == null || v.isEmpty ? 'Password required' : null,
                            ),
                          ] else ...[
                            TextFormField(
                              controller: _code,
                              decoration: const InputDecoration(
                                labelText: '6-digit code',
                                prefixIcon: Icon(Icons.verified_user_outlined),
                              ),
                              keyboardType: TextInputType.number,
                              maxLength: 6,
                              autofocus: true,
                              onFieldSubmitted: (_) => _submit(),
                              validator: (v) =>
                                  v == null || v.trim().length < 6
                                      ? 'Enter your 6-digit code'
                                      : null,
                            ),
                          ],
                          if (_error != null) ...[
                            const SizedBox(height: 12),
                            Text(_error!,
                                textAlign: TextAlign.center,
                                style: TextStyle(color: Colors.red.shade600)),
                          ],
                          const SizedBox(height: 20),
                          FilledButton(
                            onPressed: _busy ? null : _submit,
                            child: _busy
                                ? const SizedBox(
                                    height: 20,
                                    width: 20,
                                    child: CircularProgressIndicator(
                                        strokeWidth: 2, color: Colors.white),
                                  )
                                : Text(_mfaStep ? 'Verify & sign in' : 'Sign in'),
                          ),
                        ],
                      ),
                    ),
                  ),
                  if (_mfaStep) ...[
                    const SizedBox(height: 16),
                    TextButton(
                      onPressed: () => setState(() {
                        _mfaStep = false;
                        _code.clear();
                        _error = null;
                      }),
                      child: const Text('Back'),
                    ),
                  ],
                  const SizedBox(height: 20),
                  const Text(
                    'Accounts are provisioned by your administrator.',
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
