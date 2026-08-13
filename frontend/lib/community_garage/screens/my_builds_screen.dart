/// My Builds tab — the caller's own shared builds, with edit + unshare
/// (AUT-501). Tapping a card opens the post detail; the edit icon opens a
/// caption dialog.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../models.dart';
import '../social_api.dart';
import '../widgets/premium_gate.dart';
import '../widgets/social_card.dart';
import 'social_post_detail.dart';

class MyBuildsScreen extends StatefulWidget {
  const MyBuildsScreen({super.key});

  @override
  State<MyBuildsScreen> createState() => _MyBuildsScreenState();
}

class _MyBuildsScreenState extends State<MyBuildsScreen> {
  List<SocialBuild> _builds = const [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final api = SocialApi(context.read<AuthState>().api);
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final builds = await api.myPosts();
      setState(() => _builds = builds);
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } catch (_) {
      setState(
          () => _error = 'Could not reach the server. Check your connection.');
    }
    setState(() => _loading = false);
  }

  Future<void> _refresh() => _load();

  Future<void> _edit(SocialBuild build) async {
    final controller = TextEditingController(text: build.caption ?? '');
    final caption = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Edit build'),
        content: TextField(
          controller: controller,
          autofocus: true,
          maxLines: 3,
          maxLength: 1000,
          decoration: const InputDecoration(
            labelText: 'Caption',
            border: OutlineInputBorder(),
          ),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, controller.text.trim()),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (caption == null || !mounted) return;
    try {
      final updated = await SocialApi(context.read<AuthState>().api).updatePost(
          build.id,
          caption: caption.isEmpty ? null : caption);
      if (mounted) {
        setState(() => _builds = [
              for (final b in _builds) b.id == updated.id ? updated : b
            ]);
      }
    } on ApiException catch (e) {
      _toast(e.message);
    } catch (e) {
      _toast('Could not save: $e');
    }
  }

  Future<void> _delete(SocialBuild build) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Unshare build?'),
        content: Text('Remove "${build.title ?? 'this build'}" from the feed?'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Unshare')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await SocialApi(context.read<AuthState>().api).deletePost(build.id);
      if (mounted) {
        setState(() => _builds = _builds.where((b) => b.id != build.id).toList());
      }
    } catch (e) {
      _toast('Could not delete: $e');
    }
  }

  void _toast(String message) {
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    if (context.watch<AuthState>().freeAccount) return const PremiumGate();
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(_error!, textAlign: TextAlign.center),
              const SizedBox(height: 16),
              FilledButton(onPressed: _load, child: const Text('Retry')),
            ],
          ),
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: _refresh,
      child: _builds.isEmpty
          ? ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              children: const [
                SizedBox(height: 160),
                Center(
                  child: Text(
                      'You have not shared any builds yet.\nTap "Share a build" in the feed to post one.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: Colors.grey)),
                ),
              ],
            )
          : ListView.builder(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 88),
              itemCount: _builds.length,
              itemBuilder: (_, i) {
                final build = _builds[i];
                return SocialCard(
                  post: build,
                  onTap: () async {
                    await Navigator.of(context).push(MaterialPageRoute(
                        builder: (_) => SocialPostDetailScreen(
                            postId: build.id, initial: build)));
                    _refresh();
                  },
                  onEdit: () => _edit(build),
                  onDelete: () => _delete(build),
                );
              },
            ),
    );
  }
}
