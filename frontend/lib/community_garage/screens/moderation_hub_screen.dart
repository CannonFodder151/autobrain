/// Admin moderation hub (AUT-832): every reported issue post and comment with
/// the reporting reason + author. Admins can delete the reported entry or ban
/// (and unban) the author from posting in Community Garage.
library;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../core/auth_state.dart';
import '../social_api.dart';

class ModerationHubScreen extends StatefulWidget {
  const ModerationHubScreen({super.key});

  @override
  State<ModerationHubScreen> createState() => _ModerationHubScreenState();
}

class _ModerationHubScreenState extends State<ModerationHubScreen> {
  List<Map<String, dynamic>> _items = const [];
  bool _loading = true;
  String? _error;
  final Set<String> _busy = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final items =
          await SocialApi(context.read<AuthState>().api).reviewQueue();
      if (mounted) setState(() => _items = items);
    } on Exception catch (e) {
      if (mounted) setState(() => _error = 'Could not load the review queue: $e');
    }
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _guard(String label, Future<void> Function() action) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(label),
        content: const Text('This cannot be undone.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Confirm')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await action();
      if (mounted) _toast('Done.');
      await _load();
    } on Exception catch (e) {
      if (mounted) _toast('Failed: $e');
    }
  }

  void _toast(String message) {
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('To review'),
        actions: [
          IconButton(tooltip: 'Refresh', icon: const Icon(Icons.refresh), onPressed: _load),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Padding(
                  padding: const EdgeInsets.all(24),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(_error!, textAlign: TextAlign.center),
                      const SizedBox(height: 16),
                      FilledButton(onPressed: _load, child: const Text('Retry')),
                    ],
                  ),
                ))
              : _items.isEmpty
                  ? const Center(
                      child: Text('Nothing to review — reports will appear here.',
                          style: TextStyle(color: Colors.grey)))
                  : RefreshIndicator(
                      onRefresh: _load,
                      child: ListView.separated(
                        padding: const EdgeInsets.fromLTRB(12, 12, 12, 24),
                        itemCount: _items.length,
                        separatorBuilder: (_, __) => const SizedBox(height: 10),
                        itemBuilder: (_, i) => _tile(_items[i]),
                      ),
                    ),
    );
  }

  Widget _tile(Map<String, dynamic> item) {
    final scheme = Theme.of(context).colorScheme;
    final isComment = item['kind'] == 'comment';
    final author = isComment
        ? (item['comment_author_display_name'] as String? ?? 'Unknown')
        : (item['post_author_display_name'] as String? ?? 'Unknown');
    final authorId = isComment
        ? (item['comment_author_user_id'] as String?)
        : (item['post_author_user_id'] as String?);
    final postId = item['post_id'] as String? ?? '';
    final commentId = item['comment_id'] as String?;
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: isComment ? scheme.secondaryContainer : scheme.tertiaryContainer,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(isComment ? 'REPLY' : 'POST',
                      style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700,
                          color: scheme.onSecondaryContainer)),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(author,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                ),
              ],
            ),
            const SizedBox(height: 8),
            if (isComment)
              Text(item['comment_body'] as String? ?? '',
                  maxLines: 3, overflow: TextOverflow.ellipsis)
            else
              Text(item['post_title'] as String? ?? '',
                  maxLines: 3, overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontWeight: FontWeight.w600)),
            const SizedBox(height: 6),
            Text('Reported: ${item['reason'] as String? ?? ''}',
                style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
            if (authorId == null)
              const SizedBox(height: 8)
            else
              Align(
                alignment: Alignment.centerRight,
                child: Wrap(
                  spacing: 8,
                  children: [
                    TextButton.icon(
                      onPressed: _busy.contains(postId) ? null : () => _guard(
                          isComment ? 'Delete this reply?' : 'Delete this post?',
                          () async {
                        setState(() => _busy.add(postId));
                        try {
                          if (isComment && commentId != null) {
                            await SocialApi(context.read<AuthState>().api)
                                .adminDeleteComment(commentId);
                          } else {
                            await SocialApi(context.read<AuthState>().api)
                                .adminDeletePost(postId);
                          }
                        } finally {
                          if (mounted) setState(() => _busy.remove(postId));
                        }
                      }),
                      icon: const Icon(Icons.delete_outline, size: 18),
                      label: const Text('Delete'),
                      style: TextButton.styleFrom(foregroundColor: scheme.error),
                    ),
                    TextButton.icon(
                      onPressed: _busy.contains(authorId) ? null : () => _guard(
                          'Ban this user from posting?',
                          () async {
                        setState(() => _busy.add(authorId));
                        try {
                          await SocialApi(context.read<AuthState>().api)
                              .socialBan(authorId);
                        } finally {
                          if (mounted) setState(() => _busy.remove(authorId));
                        }
                      }),
                      icon: const Icon(Icons.block, size: 18),
                      label: const Text('Ban user'),
                      style: TextButton.styleFrom(foregroundColor: scheme.error),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}
