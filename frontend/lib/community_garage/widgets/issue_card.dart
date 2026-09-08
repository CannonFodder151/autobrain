/// Issues Blog list card — blog-archive style (AUT-627). Title, excerpt,
/// author "Name from Server", tags, comment count, status badge, date.
library;

import 'package:flutter/material.dart';

import '../models.dart';

/// Status badge with a deterministic colour + icon per state.
class IssueStatusBadge extends StatelessWidget {
  const IssueStatusBadge({super.key, required this.status});
  final IssueStatus status;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final (label, color, icon) = switch (status) {
      IssueStatus.open => ('Open', scheme.primary, Icons.circle_outlined),
      IssueStatus.answered =>
        ('Answered', Colors.amber.shade800, Icons.check_circle_outline),
      IssueStatus.resolved => ('Resolved', Colors.green.shade700, Icons.check_circle),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withOpacity(0.12),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 4),
          Text(label, style: TextStyle(fontSize: 11, fontWeight: FontWeight.w700, color: color)),
        ],
      ),
    );
  }
}

class IssueCard extends StatelessWidget {
  const IssueCard({super.key, required this.post, required this.onTap});

  final SocialIssuePost post;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 10),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Text(post.title,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            fontSize: 16, fontWeight: FontWeight.w800)),
                  ),
                  const SizedBox(width: 8),
                  IssueStatusBadge(status: post.status),
                ],
              ),
              if (post.excerpt.isNotEmpty) ...[
                const SizedBox(height: 6),
                Text(post.excerpt,
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant)),
              ],
              const SizedBox(height: 10),
              Text(
                '${post.authorDisplayName}'
                '${post.serverName != null ? ' · ${post.serverName}' : ''}'
                ' · ${socialRelativeTime(post.createdAt)}',
                style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant),
              ),
              if (post.tags.isNotEmpty) ...[
                const SizedBox(height: 8),
                Wrap(
                  spacing: 6,
                  runSpacing: 4,
                  children: [
                    for (final t in post.tags.take(4))
                      Chip(
                        label: Text(t,
                            style: const TextStyle(fontSize: 11)),
                        visualDensity: VisualDensity.compact,
                        materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      ),
                    if (post.tags.length > 4)
                      Text('+${post.tags.length - 4}',
                          style: TextStyle(
                              fontSize: 11, color: scheme.onSurfaceVariant)),
                  ],
                ),
              ],
              const SizedBox(height: 6),
              Row(
                children: [
                  Icon(Icons.chat_bubble_outline, size: 15, color: scheme.onSurfaceVariant),
                  const SizedBox(width: 4),
                  Text('${post.commentCount}',
                      style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
