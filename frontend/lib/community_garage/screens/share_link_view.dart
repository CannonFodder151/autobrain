/// Share-link viewer — resolves `{origin}/s/{token}` into a read-only build
/// detail. Loading → post → not-found; origin unavailable shows not-found
/// (no degraded content, per board decision).
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../models.dart';
import '../social_api.dart';
import '../widgets/premium_gate.dart';
import 'social_post_detail.dart';

class ShareLinkView extends StatefulWidget {
  const ShareLinkView({super.key, this.token});

  final String? token;

  @override
  State<ShareLinkView> createState() => _ShareLinkViewState();
}

class _ShareLinkViewState extends State<ShareLinkView> {
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _resolve();
  }

  Future<void> _resolve() async {
    final token = widget.token;
    if (token == null) {
      setState(() {
        _error = 'No share token in the link.';
        _loading = false;
      });
      return;
    }
    final auth = context.read<AuthState>();
    if (auth.freeAccount) {
      setState(() => _loading = false);
      return;
    }
    try {
      final build = await SocialApi(auth.api).resolveShare(token);
      if (mounted) {
        Navigator.of(context).pushReplacement(MaterialPageRoute(
            builder: (_) => SocialPostDetailScreen(
                postId: build.id, initial: build)));
      }
      return;
    } on ApiException catch (e) {
      if (mounted) {
        setState(() => _error = e.message.contains('Build not found')
            ? 'This build could not be found.'
            : e.message);
      }
    } catch (_) {
      if (mounted) setState(() => _error = 'Could not reach the server.');
    }
    setState(() => _loading = false);
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    return Scaffold(
      appBar: AppBar(title: const Text('Shared build')),
      body: auth.freeAccount
          ? const PremiumGate()
          : _loading
              ? const Center(child: CircularProgressIndicator())
              : _error != null
                  ? Center(
                      child: Padding(
                        padding: const EdgeInsets.all(24),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(Icons.link_off, size: 64),
                            const SizedBox(height: 12),
                            Text(_error!, textAlign: TextAlign.center),
                          ],
                        ),
                      ),
                    )
                  : const SizedBox.shrink(),
    );
  }
}
