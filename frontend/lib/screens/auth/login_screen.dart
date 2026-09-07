import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/auth_state.dart';
import '../../core/config.dart';
import 'reset_password.dart';
import 'signup_screen.dart';

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
  final _emailNode = FocusNode();
  final _codeNode = FocusNode();
  bool _busy = false;
  bool _mfaStep = false;
  bool _mfaSetupStep = false;
  String? _mfaToken;
  String? _mfaQr;
  String? _mfaSecret;
  String? _error;
  bool _serverOffline = false;

  bool get _isDemo =>
      AppConfig.apiBase.contains('demo.autobrainservice.app');

  @override
  void initState() {
    super.initState();
    if (_isDemo) {
      // Demo build auto-fills the read-only demo account.
      _email.text = 'demo@autobrainservice.app';
      _password.text = 'demo';
    }
    // Focus + select the email field so web autofill always lands in it.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _emailNode.requestFocus();
      _email.selection =
          TextSelection(baseOffset: 0, extentOffset: _email.text.length);
    });
  }

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _code.dispose();
    _emailNode.dispose();
    _codeNode.dispose();
    super.dispose();
  }

  Future<void> _afterAuth() async {
    // Post-login cleanup: un-spin the button and drop back to the root route
    // (which swaps to HomeScreen once logged in).
    if (!mounted) return;
    if (!context.read<AuthState>().isLoggedIn) return;
    setState(() {
      _busy = false;
      _error = null;
    });
    if (Navigator.of(context).canPop()) {
      Navigator.of(context).popUntil((r) => r.isFirst);
    }
  }

  Future<void> _submit() async {
    if (_busy) return;
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
      _serverOffline = false;
    });
    final auth = context.read<AuthState>();
    if (_mfaSetupStep) {
      final ok = await auth.completeMfaSetup(_mfaToken!, _code.text.trim());
      if (!mounted) return;
      if (ok) {
        await _afterAuth();
      } else {
        setState(() {
          _busy = false;
          _error = 'Invalid verification code';
        });
      }
      return;
    }
    if (_mfaStep) {
      final ok = await auth.verifyMfa(_mfaToken!, _code.text.trim());
      if (!mounted) return;
      if (ok) {
        await _afterAuth();
      } else {
        setState(() {
          _busy = false;
          _error = 'Invalid verification code';
        });
      }
      return;
    }
    final outcome = await auth.login(_email.text, _password.text);
    if (!mounted) return;
    if (outcome == LoginOutcome.mfaSetupRequired) {
      _mfaToken = auth.mfaTokenHint;
      final setup = await auth.startMfaSetup(_mfaToken!);
      if (!mounted) return;
      if (setup == null) {
        setState(() {
          _busy = false;
          _error = 'Could not start MFA setup. Contact your administrator.';
        });
        return;
      }
      setState(() {
        _mfaSetupStep = true;
        _mfaQr = setup['qr_data_url'] as String?;
        _mfaSecret = setup['secret'] as String?;
        _busy = false;
      });
      _focusCode();
    } else if (outcome == LoginOutcome.mfaRequired) {
      setState(() {
        _mfaStep = true;
        _mfaToken = auth.mfaTokenHint;
        _busy = false;
      });
      _focusCode();
    } else if (outcome == LoginOutcome.serverOffline) {
      setState(() {
        _busy = false;
        _serverOffline = true;
        _error = 'Backend server offline. Please check your connection and try again.';
      });
    } else if (outcome == LoginOutcome.failed) {
      setState(() {
        _busy = false;
        _error = 'Invalid email or password';
      });
    } else if (outcome == LoginOutcome.ok) {
      await _afterAuth();
    }
  }

  void _focusCode() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _codeNode.requestFocus();
    });
  }

  Future<void> _openSupport() async {
    final ok = await launchUrl(
      Uri.parse('https://autobrainservice.app/contact.html?source=app'),
      mode: LaunchMode.externalApplication,
    );
    if (!ok && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not open the support page.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final auth = context.watch<AuthState>();
    return Scaffold(
      body: Container(
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [scheme.primary, scheme.primary.withOpacity(0.75), scheme.secondary.withOpacity(0.6)],
          ),
        ),
        child: SafeArea(
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 480),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withOpacity(0.15),
                          blurRadius: 24,
                          offset: const Offset(0, 8),
                        ),
                      ],
                    ),
                    child: ClipOval(
                      child: Image.asset(
                        'assets/logo.png',
                        width: 72,
                        height: 72,
                        fit: BoxFit.cover,
                      ),
                    ),
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
                    _mfaSetupStep
                        ? 'Enable two-factor authentication'
                        : _mfaStep
                            ? 'Enter your verification code'
                            : 'Your garage, your data, AI-powered.',
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
                          color: Colors.black.withOpacity(0.18),
                          blurRadius: 32,
                          offset: const Offset(0, 12),
                        ),
                      ],
                    ),
                    child: AutofillGroup(
                      child: Form(
                        key: _formKey,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                          if (_mfaSetupStep) ...[
                            if (_mfaQr != null)
                              Center(
                                child: Image.memory(
                                  _dataUriBytes(_mfaQr!),
                                  width: 200,
                                  height: 200,
                                  gaplessPlayback: true,
                                  fit: BoxFit.contain,
                                ),
                              ),
                            const SizedBox(height: 12),
                            Text(
                              'Scan with Google Authenticator, Authy or 1Password, then enter the 6-digit code.',
                              style: TextStyle(
                                fontSize: 13,
                                color: Theme.of(context).colorScheme.onSurfaceVariant,
                              ),
                            ),
                            if (_mfaSecret != null) ...[
                              const SizedBox(height: 6),
                              SelectableText(
                                'Secret: $_mfaSecret',
                                style: TextStyle(
                                  fontSize: 12,
                                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                                ),
                              ),
                            ],
                            const SizedBox(height: 14),
                            TextFormField(
                              controller: _code,
                              focusNode: _codeNode,
                              decoration: const InputDecoration(
                                labelText: '6-digit code',
                                prefixIcon: Icon(Icons.verified_user_outlined),
                              ),
                              keyboardType: TextInputType.number,
                              maxLength: 6,
                              autofocus: true,
                              autofillHints: const [AutofillHints.oneTimeCode],
                              onFieldSubmitted: (_) => _submit(),
                              validator: (v) =>
                                  v == null || v.trim().length < 6
                                      ? 'Enter your 6-digit code'
                                      : null,
                            ),
                          ] else if (_mfaStep) ...[
                            TextFormField(
                              controller: _code,
                              focusNode: _codeNode,
                              decoration: const InputDecoration(
                                labelText: '6-digit code',
                                prefixIcon: Icon(Icons.verified_user_outlined),
                              ),
                              keyboardType: TextInputType.number,
                              maxLength: 6,
                              autofocus: true,
                              autofillHints: const [AutofillHints.oneTimeCode],
                              onFieldSubmitted: (_) => _submit(),
                              validator: (v) =>
                                  v == null || v.trim().length < 6
                                      ? 'Enter your 6-digit code'
                                      : null,
                            ),
                          ] else ...[
                            TextFormField(
                              controller: _email,
                              focusNode: _emailNode,
                              decoration: const InputDecoration(
                                labelText: 'Email',
                                prefixIcon: Icon(Icons.mail_outline),
                              ),
                              keyboardType: TextInputType.emailAddress,
                              autofillHints: const [AutofillHints.username],
                              textInputAction: TextInputAction.done,
                              onFieldSubmitted: (_) => _submit(),
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
                              autocorrect: false,
                              enableSuggestions: false,
                              autofillHints: const [AutofillHints.password],
                              textInputAction: TextInputAction.done,
                              onFieldSubmitted: (_) => _submit(),
                              validator: (v) =>
                                  v == null || v.isEmpty ? 'Password required' : null,
                            ),
                          ],
                          if (_error != null) ...[
                            const SizedBox(height: 12),
                            Text(_error!,
                                textAlign: TextAlign.center,
                                style: TextStyle(color: Colors.red.shade600)),
                            if (_serverOffline) ...[
                              const SizedBox(height: 8),
                              OutlinedButton.icon(
                                onPressed: _openSupport,
                                icon: const Icon(Icons.support_agent, size: 18),
                                label: const Text('Contact support'),
                              ),
                            ],
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
                                : Text(_mfaSetupStep
                                    ? 'Enable MFA & sign in'
                                    : _mfaStep
                                        ? 'Verify & sign in'
                                        : 'Sign in'),
                          ),
                          if (!_mfaStep && !_mfaSetupStep) ...[
                            const SizedBox(height: 8),
                            TextButton(
                              onPressed: () => Navigator.of(context).push(
                                MaterialPageRoute(
                                  builder: (_) => const ForgotPasswordScreen(),
                                ),
                              ),
                              child: const Text('Forgot password?'),
                            ),
                            if (auth.signupEnabled) ...[
                              const SizedBox(height: 4),
                              TextButton(
                                onPressed: () => Navigator.of(context).push(
                                  MaterialPageRoute(
                                    builder: (_) => const SignupScreen(),
                                  ),
                                ),
                                child: const Text('New here? Create a free account'),
                              ),
                            ],
                          ],
                          ],
                        ),
                      ),
                    ),
                  ),
                  if (_mfaStep || _mfaSetupStep) ...[
                    const SizedBox(height: 16),
                    TextButton(
                      onPressed: () => setState(() {
                        _mfaStep = false;
                        _mfaSetupStep = false;
                        _code.clear();
                        _error = null;
                      }),
                      child: const Text('Back'),
                    ),
                  ],
                  const SizedBox(height: 20),
                  const Text(
                    'Free tier available · Self-hosted accounts are admin-managed',
                    textAlign: TextAlign.center,
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

  static Uint8List _dataUriBytes(String dataUri) {
    final comma = dataUri.indexOf(',');
    final b64 = dataUri.substring(comma + 1);
    return base64Decode(b64);
  }
}
