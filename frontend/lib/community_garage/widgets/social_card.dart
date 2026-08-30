/// Social feed card — Facebook-style single build card (AUT-294 §4.1).
library;

import 'package:flutter/material.dart';

import '../models.dart';

class SocialCard extends StatelessWidget {
  const SocialCard({
    super.key,
    required this.post,
    required this.onTap,
    this.onShare,
    this.onEdit,
    this.onDelete,
  });

  final SocialBuild post;
  final VoidCallback onTap;
  final VoidCallback? onShare;
  final VoidCallback? onEdit;
  final VoidCallback? onDelete;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 10, 12, 8),
              child: Row(
                children: [
                  CircleAvatar(
                    radius: 18,
                    child: Text(
                      _initial(post.authorDisplayName ?? '?'),
                      style: const TextStyle(fontWeight: FontWeight.w700),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(post.authorDisplayName ?? 'Unknown',
                            style: const TextStyle(fontWeight: FontWeight.w700)),
                        Text(
                          '${post.serverName ?? 'Unknown server'}'
                          '${post.origin == 'remote' ? ' · federated' : ''}'
                          ' · ${socialRelativeTime(post.createdAt)}',
                          style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
                        ),
                      ],
                    ),
                  ),
                  if (post.isRemote)
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: scheme.secondaryContainer,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text('Federated',
                          style: TextStyle(fontSize: 10, color: scheme.onSecondaryContainer)),
                    ),
                ],
              ),
            ),
            if (post.photos.isNotEmpty)
              _PhotoGrid(photos: post.photos.take(3).toList()),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (post.snapshot.makeModel.isNotEmpty)
                    Text(post.snapshot.makeModel,
                        style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 15)),
                  if (post.caption != null && post.caption!.isNotEmpty) ...[
                    const SizedBox(height: 2),
                    Text(post.caption!, maxLines: 2, overflow: TextOverflow.ellipsis),
                  ],
                  if (post.snapshot.mods.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 6,
                      runSpacing: 4,
                      children: [
                        for (final m in post.snapshot.mods.take(4))
                          Chip(
                            label: Text(m['name']?.toString() ?? 'mod',
                                style: const TextStyle(fontSize: 11)),
                            visualDensity: VisualDensity.compact,
                            padding: EdgeInsets.zero,
                            materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                          ),
                        if (post.snapshot.mods.length > 4)
                          Text('+${post.snapshot.mods.length - 4} more',
                              style: TextStyle(fontSize: 11, color: scheme.onSurfaceVariant)),
                      ],
                    ),
                  ],
                ],
              ),
            ),
            Divider(height: 1, color: scheme.outlineVariant),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8),
              child: Row(
                children: [
                  _IconStat(icon: Icons.favorite, count: post.likeCount),
                  const SizedBox(width: 12),
                  _IconStat(icon: Icons.chat_bubble_outline, count: post.commentCount),
                  const Spacer(),
                  IconButton(
                    icon: const Icon(Icons.share, size: 20),
                    tooltip: 'Share link',
                    onPressed: onShare,
                  ),
                  if (onEdit != null)
                    IconButton(
                      icon: const Icon(Icons.edit_outlined, size: 20),
                      tooltip: 'Edit build',
                      onPressed: onEdit,
                    ),
                  if (onDelete != null)
                    IconButton(
                      icon: const Icon(Icons.delete_outline, size: 20),
                      tooltip: 'Unshare build',
                      onPressed: onDelete,
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _initial(String name) =>
      name.isEmpty ? '?' : name[0].toUpperCase();
}

class _IconStat extends StatelessWidget {
  const _IconStat({required this.icon, required this.count});
  final IconData icon;
  final int count;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.all(6),
        child: Row(
          children: [
            Icon(icon, size: 18),
            const SizedBox(width: 4),
            Text('$count', style: const TextStyle(fontSize: 13)),
          ],
        ),
      );
}

class _PhotoGrid extends StatelessWidget {
  const _PhotoGrid({required this.photos});
  final List<String> photos;

  @override
  Widget build(BuildContext context) {
    if (photos.length == 1) {
      return AspectRatio(
        aspectRatio: 16 / 10,
        child: Image.network(photos[0], fit: BoxFit.cover,
            errorBuilder: (_, __, ___) => const SizedBox.shrink()),
      );
    }
    return SizedBox(
      height: 220,
      child: Row(
        children: [
          Expanded(
            flex: 2,
            child: Image.network(photos[0], fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => const SizedBox.shrink()),
          ),
          const SizedBox(width: 2),
          Expanded(
            child: Column(
              children: [
                if (photos.length > 1)
                  Expanded(
                    child: Image.network(photos[1], fit: BoxFit.cover,
                        errorBuilder: (_, __, ___) => const SizedBox.shrink()),
                  ),
                if (photos.length > 2) ...[
                  const SizedBox(height: 2),
                  Expanded(
                    child: Stack(
                      fit: StackFit.expand,
                      children: [
                        Image.network(photos[2], fit: BoxFit.cover,
                            errorBuilder: (_, __, ___) => const SizedBox.shrink()),
                        if (photos.length > 3)
                          Container(
                            color: Colors.black54,
                            alignment: Alignment.center,
                            child: Text('+${photos.length - 3}',
                                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w800)),
                          ),
                      ],
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
