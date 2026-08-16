/// Social post detail — photo gallery + spec sheet + comments + likes.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../models.dart';
import '../social_api.dart';
import '../widgets/premium_gate.dart';
import 'social_compose.dart';

class SocialPostDetailScreen extends StatefulWidget {
  const SocialPostDetailScreen({super.key, required this.postId, this.initial});

  final String postId;
  final SocialBuild? initial;

  @override
  State<SocialPostDetailScreen> createState() => _SocialPostDetailScreenState();
}

class _SocialPostDetailScreenState extends State<SocialPostDetailScreen> {
  late SocialBuild? _build = widget.initial;
  List<SocialComment> _comments = const [];
  bool _loading = true;
  bool _loadingComments = false;
  bool _disabled = false;
  final _commentController = TextEditingController();
  int _photoIndex = 0;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _commentController.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    final auth = context.read<AuthState>();
    if (auth.freeAccount) {
      setState(() => _loading = false);
      return;
    }
    final api = SocialApi(auth.api);
    try {
      final build = await api.getPost(widget.postId);
      setState(() {
        _build = build;
        _loading = false;
      });
    } on ApiException catch (e) {
      if (e.message.contains('Disabled by your admin')) {
        setState(() {
          _disabled = true;
          _loading = false;
        });
        return;
      }
      setState(() => _loading = false);
      _toast(e.message);
      return;
    } catch (_) {
      setState(() => _loading = false);
    }
    _loadComments();
  }

  Future<void> _loadComments() async {
    setState(() => _loadingComments = true);
    try {
      final comments =
          await SocialApi(context.read<AuthState>().api).comments(widget.postId);
      if (mounted) setState(() => _comments = comments);
    } catch (_) {}
    setState(() => _loadingComments = false);
  }

  Future<void> _toggleLike() async {
    final build = _build;
    if (build == null) return;
    try {
      final result =
          await SocialApi(context.read<AuthState>().api).toggleLike(build.id);
      setState(() {
        _build = build.copyWith(likedByMe: result.liked, likeCount: result.count);
      });
    } catch (e) {
      _toast('Could not update like: $e');
    }
  }

  Future<void> _addComment() async {
    final body = _commentController.text.trim();
    if (body.isEmpty) return;
    _commentController.clear();
    try {
      final comment = await SocialApi(context.read<AuthState>().api)
          .addComment(widget.postId, body);
      setState(() => _comments = [..._comments, comment]);
    } catch (e) {
      _toast('Could not post comment: $e');
    }
  }

  void _toast(String message) {
    if (mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(message)));
    }
  }

  Future<void> _report() async {
    final controller = TextEditingController();
    final reason = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Report this post'),
        content: TextField(
          controller: controller,
          autofocus: true,
          maxLines: 3,
          maxLength: 200,
          decoration: const InputDecoration(
            labelText: 'Reason',
            hintText: 'e.g. spam, misleading, abuse',
            border: OutlineInputBorder(),
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, controller.text.trim()),
            child: const Text('Report'),
          ),
        ],
      ),
    );
    if (reason == null || reason.isEmpty || !mounted) return;
    try {
      await SocialApi(context.read<AuthState>().api)
          .reportBuild(widget.postId, reason);
      _toast('Thanks — your report has been submitted for review.');
    } on ApiException catch (e) {
      _toast(e.message);
    } catch (e) {
      _toast('Could not submit report: $e');
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthState>();
    final build = _build;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Build details'),
        actions: [
          if (auth.premium && build != null && !_disabled)
            PopupMenuButton<String>(
              tooltip: 'More options',
              onSelected: (value) {
                if (value == 'report') _report();
              },
              itemBuilder: (_) => const [
                PopupMenuItem(value: 'report', child: Text('Report post')),
              ],
            ),
        ],
      ),
      body: auth.freeAccount
          ? const PremiumGate()
          : _disabled
              ? const Center(
                  child:
                      Text('Community Garage has been disabled by your admin.'))
              : _loading
                  ? const Center(child: CircularProgressIndicator())
                  : build == null
                      ? const Center(child: Text('Post not found'))
                      : _content(build, auth),
    );
  }

  Widget _content(SocialBuild build, AuthState auth) {
    final scheme = Theme.of(context).colorScheme;
    return ListView(
      children: [
        if (build.photos.isNotEmpty) _gallery(build.photos),
        Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '${build.authorDisplayName ?? 'Unknown'}'
                '${build.serverName != null ? ' · ${build.serverName}' : ''}'
                ' · ${socialRelativeTime(build.createdAt)}',
                style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 13),
              ),
              const SizedBox(height: 6),
              if (build.snapshot.makeModel.isNotEmpty)
                Text(build.snapshot.makeModel,
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
              if (build.caption != null && build.caption!.isNotEmpty) ...[
                const SizedBox(height: 6),
                Text(build.caption!),
              ],
              const SizedBox(height: 16),
              if (build.snapshot.specs.isNotEmpty) _specSheet(build.snapshot.specs),
              if (build.snapshot.mods.isNotEmpty) ...[
                const SizedBox(height: 16),
                Text('Mods', style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (final m in build.snapshot.mods)
                      Chip(
                        label: Text(
                            m['name']?.toString() ?? 'mod',
                            style: const TextStyle(fontSize: 13)),
                      ),
                  ],
                ),
              ],
              const Divider(height: 32),
              Row(
                children: [
                  IconButton(
                    onPressed: auth.premium ? _toggleLike : null,
                    icon: Icon(build.likedByMe
                        ? Icons.favorite
                        : Icons.favorite_border),
                    color: build.likedByMe ? Colors.red : null,
                  ),
                  Text('${build.likeCount}'),
                  const SizedBox(width: 16),
                  const Icon(Icons.chat_bubble_outline),
                  const SizedBox(width: 6),
                  Text('${_comments.length}'),
                ],
              ),
              const Divider(height: 8),
            ],
          ),
        ),
        if (auth.premium) ...[
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: TextField(
              controller: _commentController,
              decoration: InputDecoration(
                hintText: 'Add a comment…',
                suffixIcon: IconButton(
                  icon: const Icon(Icons.send),
                  onPressed: _addComment,
                ),
              ),
            ),
          ),
          if (_loadingComments)
            const Padding(
              padding: EdgeInsets.all(12),
              child: Center(child: CircularProgressIndicator()),
            ),
          for (final c in _comments)
            ListTile(
              leading: CircleAvatar(
                child: Text(c.authorDisplayName.isEmpty
                    ? '?'
                    : c.authorDisplayName[0].toUpperCase()),
              ),
              title: Text(c.authorDisplayName,
                  style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
              subtitle: Text(c.body),
              trailing: c.serverName != null
                  ? Text(c.serverName!,
                      style: const TextStyle(fontSize: 11, color: Colors.grey))
                  : null,
            ),
        ] else
          const Padding(
            padding: EdgeInsets.all(16),
            child: Center(
              child: Text('Comments are a premium feature.',
                  style: TextStyle(color: Colors.grey)),
            ),
          ),
        const SizedBox(height: 32),
      ],
    );
  }

  Widget _gallery(List<String> photos) {
    return Column(
      children: [
        AspectRatio(
          aspectRatio: 4 / 3,
          child: PageView.builder(
            itemCount: photos.length,
            onPageChanged: (i) => setState(() => _photoIndex = i),
            itemBuilder: (_, i) => Image.network(photos[i],
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => const SizedBox.shrink()),
          ),
        ),
        if (photos.length > 1)
          Padding(
            padding: const EdgeInsets.all(4),
            child: Text('${_photoIndex + 1} / ${photos.length}',
                style: const TextStyle(fontSize: 12, color: Colors.grey)),
          ),
      ],
    );
  }

  Widget _specSheet(Map<String, dynamic> specs) {
    final rows = <String, String>{
      if (specs['year'] != null) 'Year': '${specs['year']}',
      if (specs['colour'] != null) 'Colour': '${specs['colour']}',
      if (specs['engine'] != null) 'Engine': '${specs['engine']}',
      if (specs['transmission'] != null)
        'Transmission': '${specs['transmission']}',
      if (specs['body_type'] != null) 'Body': '${specs['body_type']}',
      if (specs['odometer_km'] != null)
        'Odometer': '${specs['odometer_km']} km',
    };
    if (rows.isEmpty) return const SizedBox.shrink();
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Specs', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            for (final e in rows.entries)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 2),
                child: Row(
                  children: [
                    SizedBox(
                      width: 110,
                      child: Text(e.key,
                          style: TextStyle(color: Theme.of(context).colorScheme.onSurfaceVariant)),
                    ),
                    Text(e.value),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}
