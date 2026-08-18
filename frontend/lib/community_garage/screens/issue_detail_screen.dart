/// Issue detail — blog-post layout (title, meta, body, vehicle context, tags)
/// + chronological comment thread. Mark-answer affordance for eligible authors,
/// report action, resolved banner pointing at the pinned answer (AUT-627).
/// Replies may attach one photo each (AUT-736).
library;

import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../../core/api_client.dart';
import '../../core/auth_state.dart';
import '../models.dart';
import '../social_api.dart';
import '../widgets/issue_card.dart';
import '../widgets/premium_gate.dart';

class IssueDetailScreen extends StatefulWidget {
  const IssueDetailScreen({super.key, required this.postId, this.initial});

  final String postId;
  final SocialIssuePost? initial;

  @override
  State<IssueDetailScreen> createState() => _IssueDetailScreenState();
}

class _IssueDetailScreenState extends State<IssueDetailScreen> {
  late SocialIssuePost? _post = widget.initial;
  bool _loading = true;
  bool _disabled = false;
  final _commentController = TextEditingController();
  bool _commenting = false;
  ({String name, String mime, Uint8List bytes})? _pickedPhoto;

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

  Future<void> _pickPhoto() async {
    if (_commenting) return;
    final file = await ImagePicker().pickImage(
      source: ImageSource.gallery,
      maxWidth: 2048,
      imageQuality: 82,
    );
    if (file == null || !mounted) return;
    final bytes = await file.readAsBytes();
    if (!mounted) return;
    setState(() => _pickedPhoto = (
      name: file.name,
      mime: (file.mimeType?.trim().isNotEmpty ?? false) ? file.mimeType! : 'image/jpeg',
      bytes: bytes,
    ));
  }

  Future<void> _load() async {
    final auth = context.read<AuthState>();
    if (auth.freeAccount) {
      setState(() => _loading = false);
      return;
    }
    final api = SocialApi(auth.api);
    try {
      final post = await api.getIssue(widget.postId);
      setState(() {
        _post = post;
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
    } catch (_) {
      setState(() => _loading = false);
    }
  }

  Future<void> _addComment() async {
    final body = _commentController.text.trim();
    if (body.isEmpty && _pickedPhoto == null) return;
    setState(() => _commenting = true);
    _commentController.clear();
    final photo = _pickedPhoto;
    _pickedPhoto = null;
    try {
      final api = SocialApi(context.read<AuthState>().api);
      String? photoId;
      if (photo != null) {
        final uploaded = await api.uploadPhoto(photo.bytes, photo.name, photo.mime);
        photoId = uploaded.id;
      }
      final comment = await api.addIssueComment(widget.postId, body, photoId: photoId);
      if (mounted) {
        setState(() {
          final post = _post!;
          _post = post.copyWith(
            comments: [...post.comments, comment],
            commentCount: post.commentCount + 1,
          );
        });
      }
    } catch (e) {
      if (photo != null) setState(() => _pickedPhoto = photo);
      _toast('Could not post comment: $e');
    }
    setState(() => _commenting = false);
  }

  Future<void> _markAnswer(SocialIssueComment comment) async {
    final post = _post;
    if (post == null) return;
    final api = SocialApi(context.read<AuthState>().api);
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Mark as the answer?'),
        content: const Text(
            'This marks the issue as resolved and pins this comment as the answer.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Mark as answer')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await api.markAnswer(post.id, comment.id);
      if (mounted) {
        setState(() {
          final updated = post.copyWith(
            status: IssueStatus.resolved,
            resolvedCommentId: comment.id,
            comments: [
              for (final c in post.comments)
                c.id == comment.id
                    ? SocialIssueComment(
                        id: c.id,
                        authorDisplayName: c.authorDisplayName,
                        serverName: c.serverName,
                        body: c.body,
                        photo: c.photo,
                        isAnswer: true,
                        isMine: c.isMine,
                        createdAt: c.createdAt,
                      )
                    : c,
            ],
          );
          _post = updated;
        });
        _toast('Marked as answered and resolved.');
      }
    } catch (e) {
      _toast('Could not mark answer: $e');
    }
  }

  Future<void> _report() async {
    final controller = TextEditingController();
    final reason = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Report this issue'),
        content: TextField(
          controller: controller,
          autofocus: true,
          maxLines: 3,
          maxLength: 200,
          decoration: const InputDecoration(
            labelText: 'Reason',
            hintText: 'e.g. spam, abuse, wrong category',
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
          .flagIssue(widget.postId, reason);
      _toast('Thanks — your report has been submitted for review.');
    } on ApiException catch (e) {
      _toast(e.message);
    } catch (e) {
      _toast('Could not submit report: $e');
    }
  }

  Future<void> _reportComment(SocialIssueComment comment) async {
    final controller = TextEditingController();
    final reason = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Report this reply'),
        content: TextField(
          controller: controller,
          autofocus: true,
          maxLines: 3,
          maxLength: 200,
          decoration: const InputDecoration(
            labelText: 'Reason',
            hintText: 'e.g. spam, abuse, wrong category',
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
          .flagIssueComment(_post!.id, comment.id, reason);
      _toast('Thanks — your report has been submitted for review.');
    } on ApiException catch (e) {
      _toast(e.message);
    } catch (e) {
      _toast('Could not submit report: $e');
    }
  }

  Future<void> _delete() async {
    final post = _post;
    if (post == null) return;
    final api = SocialApi(context.read<AuthState>().api);
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Delete issue?'),
        content: Text('Remove "${post.title}" and all its comments?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Delete')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await api.deleteIssue(post.id);
      if (mounted) {
        Navigator.of(context).pop(true);
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Issue deleted.')));
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
    final auth = context.watch<AuthState>();
    final post = _post;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Issue'),
        actions: [
          IconButton(
            tooltip: 'Report this issue',
            icon: const Icon(Icons.flag_outlined),
            onPressed: auth.premium ? _report : null,
          ),
          if (post != null && post.isMine && auth.premium)
            IconButton(
              tooltip: 'Delete issue',
              icon: const Icon(Icons.delete_outline),
              onPressed: _delete,
            ),
        ],
      ),
      body: auth.freeAccount
          ? const PremiumGate(
              lockedReason:
                  'The Issues Blog is a premium member feature — get help from real owners.')
          : _disabled
              ? const Center(
                  child: Text('Community Garage has been disabled by your admin.'))
              : _loading
                  ? const Center(child: CircularProgressIndicator())
                  : post == null
                      ? const Center(child: Text('Issue not found'))
                      : _content(post, auth),
    );
  }

  Widget _content(SocialIssuePost post, AuthState auth) {
    final scheme = Theme.of(context).colorScheme;
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 32),
      children: [
        if (post.status == IssueStatus.resolved) _resolvedBanner(post),
        Row(
          children: [
            Expanded(
              child: Text(post.title,
                  style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800)),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Text(
          'By ${post.authorDisplayName}'
          '${post.serverName != null ? ' · ${post.serverName}' : ''}'
          ' · ${socialRelativeTime(post.createdAt)}',
          style: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant),
        ),
        const SizedBox(height: 4),
        Align(
          alignment: Alignment.centerLeft,
          child: IssueStatusBadge(status: post.status),
        ),
        if (post.snapshot.makeModel.isNotEmpty) ...[
          const SizedBox(height: 16),
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: scheme.surfaceContainerHighest,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Row(
              children: [
                Icon(Icons.directions_car, size: 18, color: scheme.onSurfaceVariant),
                const SizedBox(width: 8),
                Text('Vehicle: ${post.snapshot.makeModel}',
                    style: const TextStyle(fontWeight: FontWeight.w600)),
              ],
            ),
          ),
        ],
        const SizedBox(height: 12),
        Text(post.body, style: const TextStyle(fontSize: 15, height: 1.45)),
        if (post.photos.isNotEmpty) ...[
          const SizedBox(height: 14),
          _photoGallery(post.photos),
        ],
        if (post.tags.isNotEmpty) ...[
          const SizedBox(height: 14),
          Wrap(
            spacing: 6,
            runSpacing: 4,
            children: [
              for (final t in post.tags)
                Chip(
                  label: Text(t, style: const TextStyle(fontSize: 12)),
                  visualDensity: VisualDensity.compact,
                ),
            ],
          ),
        ],
        const Divider(height: 32),
        Text('${post.commentCount} ${post.commentCount == 1 ? 'reply' : 'replies'}',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        if (auth.premium) ...[
          if (_pickedPhoto != null) ...[
            Align(
              alignment: Alignment.centerLeft,
              child: Stack(
                children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: Image.memory(_pickedPhoto!.bytes,
                        width: 84, height: 84, fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) => const SizedBox(
                            width: 84, height: 84, child: Icon(Icons.image))),
                  ),
                  Positioned(
                    top: 2,
                    right: 2,
                    child: InkWell(
                      onTap: () => setState(() => _pickedPhoto = null),
                      child: const CircleAvatar(
                        radius: 10,
                        backgroundColor: Colors.black54,
                        child: Icon(Icons.close, size: 14, color: Colors.white),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 8),
          ],
          TextField(
            controller: _commentController,
            decoration: InputDecoration(
              hintText: 'Share your experience or advice…',
              prefixIcon: IconButton(
                tooltip: _pickedPhoto != null
                    ? 'One photo per reply (attached)'
                    : 'Attach a photo',
                icon: Icon(_pickedPhoto != null
                    ? Icons.photo
                    : Icons.add_photo_alternate_outlined),
                onPressed: _pickedPhoto != null ? null : _pickPhoto,
              ),
              suffixIcon: _commenting
                  ? const Padding(
                      padding: EdgeInsets.all(12),
                      child: SizedBox(
                          width: 18, height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2)),
                    )
                  : IconButton(icon: const Icon(Icons.send), onPressed: _addComment),
              isDense: true,
              border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
            ),
          ),
          const SizedBox(height: 12),
        ],
        if (post.comments.isEmpty)
          Text('No replies yet — be the first to help.',
              style: TextStyle(color: scheme.onSurfaceVariant))
        else
          for (final c in post.comments) _commentTile(post, c, auth),
        const SizedBox(height: 24),
      ],
    );
  }

  Widget _photoGallery(List<String> photos) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(10),
      child: AspectRatio(
        aspectRatio: 4 / 3,
        child: PageView.builder(
          itemCount: photos.length,
          itemBuilder: (_, i) => Image.network(photos[i],
              fit: BoxFit.cover,
              errorBuilder: (_, __, ___) => const SizedBox.shrink()),
        ),
      ),
    );
  }

  Widget _resolvedBanner(SocialIssuePost post) {
    final green = Colors.green.shade700;
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: green.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          Icon(Icons.check_circle, color: green),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              post.resolvedCommentId != null
                  ? 'This issue is resolved — see the pinned answer below.'
                  : 'This issue is resolved.',
              style: TextStyle(color: green, fontWeight: FontWeight.w700),
            ),
          ),
        ],
      ),
    );
  }

  void _viewPhoto(String url) {
    showDialog<void>(
      context: context,
      builder: (_) => Dialog(
        backgroundColor: Colors.black,
        insetPadding: const EdgeInsets.all(12),
        child: InteractiveViewer(
          maxScale: 5,
          child: Image.network(url,
              fit: BoxFit.contain,
              loadingBuilder: (_, child, progress) => progress == null
                  ? child
                  : const Center(child: CircularProgressIndicator()),
              errorBuilder: (_, __, ___) => const Center(
                  child: Icon(Icons.broken_image, color: Colors.white54))),
        ),
      ),
    );
  }

  Widget _commentTile(SocialIssuePost post, SocialIssueComment c, AuthState auth) {
    final scheme = Theme.of(context).colorScheme;
    final isAnswer = c.isAnswer || post.resolvedCommentId == c.id;
    final canMark = auth.premium &&
        (post.isMine || c.isMine) &&
        post.status != IssueStatus.resolved &&
        !isAnswer;
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: isAnswer ? Colors.green.withValues(alpha: 0.08) : null,
        border: isAnswer ? Border.all(color: Colors.green.shade700) : null,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text('${c.authorDisplayName}'
                    '${c.serverName != null ? ' · ${c.serverName}' : ''}'
                    ' · ${socialRelativeTime(c.createdAt)}',
                    style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
              ),
              if (auth.premium)
                IconButton(
                  tooltip: 'Report this reply',
                  icon: const Icon(Icons.flag_outlined, size: 16),
                  visualDensity: VisualDensity.compact,
                  padding: EdgeInsets.zero,
                  onPressed: () => _reportComment(c),
                ),
              if (isAnswer)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                  decoration: BoxDecoration(
                    color: Colors.green.shade700,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Text('Answer',
                      style: TextStyle(
                          fontSize: 10, color: Colors.white, fontWeight: FontWeight.w700)),
                ),
            ],
          ),
          const SizedBox(height: 4),
          Text(c.body, style: const TextStyle(fontSize: 14, height: 1.4)),
          if (c.photo != null) ...[
            const SizedBox(height: 8),
            GestureDetector(
              onTap: () => _viewPhoto(c.photo!),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: Image.network(c.photo!,
                    width: 120, height: 90, fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => const SizedBox.shrink()),
              ),
            ),
          ],
          if (canMark)
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                onPressed: () => _markAnswer(c),
                icon: const Icon(Icons.check_circle_outline, size: 18),
                label: const Text('Mark as answer'),
                style: TextButton.styleFrom(foregroundColor: Colors.green.shade700),
              ),
            ),
        ],
      ),
    );
  }
}
