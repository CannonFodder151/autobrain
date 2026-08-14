/// Community Garage data models (parsed from the P1 social API).
library;

enum SocialScope { public, server, friends }

SocialScope socialScopeFrom(String? raw) {
  switch (raw) {
    case 'public':
      return SocialScope.public;
    case 'friends':
      return SocialScope.friends;
    default:
      return SocialScope.server;
  }
}

class SocialSnapshot {
  const SocialSnapshot({this.specs = const {}, this.mods = const [], this.notes});
  final Map<String, dynamic> specs;
  final List<Map<String, dynamic>> mods;
  final String? notes;

  factory SocialSnapshot.fromJson(Map<String, dynamic>? json) {
    if (json == null) return const SocialSnapshot();
    return SocialSnapshot(
      specs: (json['specs'] as Map<String, dynamic>?) ?? const {},
      mods: ((json['mods'] as List?) ?? const [])
          .map((e) => Map<String, dynamic>.from(e as Map))
          .toList(),
      notes: json['notes'] as String?,
    );
  }

  String get makeModel {
    final make = specs['make'] as String?;
    final model = specs['model'] as String?;
    return [make, model].whereType<String>().where((s) => s.isNotEmpty).join(' ')
        .trim();
  }
}

class SocialBuild {
  SocialBuild({
    required this.id,
    this.title,
    this.caption,
    this.authorDisplayName,
    this.serverName,
    this.origin,
    this.snapshot = const SocialSnapshot(),
    this.photos = const [],
    this.photoIds = const [],
    this.shareScope = const {},
    this.likeCount = 0,
    this.likedByMe = false,
    this.commentCount = 0,
    this.createdAt,
  });

  final String id;
  final String? title;
  final String? caption;
  final String? authorDisplayName;
  final String? serverName;
  final String? origin;
  final SocialSnapshot snapshot;
  final List<String> photos;
  final List<String> photoIds;
  final Map<String, bool> shareScope;
  final int likeCount;
  final bool likedByMe;
  final int commentCount;
  final DateTime? createdAt;

  bool get isRemote => origin == 'remote';
  bool get isDemo => origin == 'demo';

  SocialBuild copyWith({bool? likedByMe, int? likeCount, int? commentCount}) =>
      SocialBuild(
        id: id,
        title: title,
        caption: caption,
        authorDisplayName: authorDisplayName,
        serverName: serverName,
        origin: origin,
        snapshot: snapshot,
        photos: photos,
        photoIds: photoIds,
        shareScope: shareScope,
        likeCount: likeCount ?? this.likeCount,
        likedByMe: likedByMe ?? this.likedByMe,
        commentCount: commentCount ?? this.commentCount,
        createdAt: createdAt,
      );

  factory SocialBuild.fromJson(Map<String, dynamic> json) => SocialBuild(
        id: json['id'] as String,
        title: json['title'] as String?,
        caption: json['caption'] as String?,
        authorDisplayName: json['author_display_name'] as String?,
        serverName: json['server_name'] as String?,
        origin: json['origin'] as String?,
        snapshot:
            SocialSnapshot.fromJson(json['snapshot'] as Map<String, dynamic>?),
        photos: ((json['photos'] as List?) ?? const []).cast<String>(),
        photoIds: ((json['photo_ids'] as List?) ?? const []).cast<String>(),
        shareScope: ((json['share_scope'] as Map<String, dynamic>?) ?? const {})
            .map((k, v) => MapEntry(k, v == true)),
        likeCount: json['like_count'] as int? ?? 0,
        likedByMe: json['liked_by_me'] == true,
        commentCount: json['comment_count'] as int? ?? 0,
        createdAt:
            DateTime.tryParse(json['created_at'] as String? ?? '')?.toLocal(),
      );
}

class SocialComment {
  SocialComment({
    required this.id,
    required this.authorDisplayName,
    required this.body,
    this.serverName,
    this.createdAt,
  });

  final String id;
  final String authorDisplayName;
  final String body;
  final String? serverName;
  final DateTime? createdAt;

  factory SocialComment.fromJson(Map<String, dynamic> json) => SocialComment(
        id: json['id'] as String,
        authorDisplayName: json['author_display_name'] as String? ?? 'Unknown',
        serverName: json['server_name'] as String?,
        body: json['body'] as String? ?? '',
        createdAt:
            DateTime.tryParse(json['created_at'] as String? ?? '')?.toLocal(),
      );
}

/// Issues Blog (AUT-627) statuses, mirrored from the backend vocabulary.
enum IssueStatus { open, answered, resolved }

IssueStatus issueStatusFrom(String? raw) {
  switch (raw) {
    case 'answered':
      return IssueStatus.answered;
    case 'resolved':
      return IssueStatus.resolved;
    default:
      return IssueStatus.open;
  }
}

/// Fixed issue tag vocabulary (mirror of backend/app/social/tags.py). The
/// server validates tags against this set, so the filter chips stay in sync.
const List<String> issueTagVocabulary = [
  'engine', 'brakes', 'electrical', 'interior', 'suspension', 'transmission',
  'cooling', 'exhaust', 'fuel', 'steering', 'battery', 'starting',
  'overheating', 'tyres', 'body', 'clutch', 'oil', 'noise', 'vibration',
  'warning',
];

class SocialIssuePost {
  SocialIssuePost({
    required this.id,
    required this.title,
    required this.body,
    required this.authorDisplayName,
    required this.tags,
    required this.status,
    required this.commentCount,
    required this.isMine,
    this.serverName,
    this.origin,
    this.resolvedCommentId,
    this.snapshot = const SocialSnapshot(),
    this.photos = const [],
    this.photoIds = const [],
    this.createdAt,
    this.comments = const [],
  });

  final String id;
  final String title;
  final String body;
  final String authorDisplayName;
  final String? serverName;
  final String? origin;
  final List<String> tags;
  final IssueStatus status;
  final String? resolvedCommentId;
  final SocialSnapshot snapshot;
  final int commentCount;
  final bool isMine;
  final List<String> photos;
  final List<String> photoIds;
  final DateTime? createdAt;
  final List<SocialIssueComment> comments;

  String get excerpt => body.replaceAll(RegExp(r'\s+'), ' ').trim();

  factory SocialIssuePost.fromJson(Map<String, dynamic> json) {
    final snap = json['vehicle_snapshot'] as Map<String, dynamic>?;
    return SocialIssuePost(
      id: json['id'] as String,
      title: json['title'] as String? ?? '',
      body: json['body'] as String? ?? '',
      authorDisplayName: json['author_display_name'] as String? ?? 'Unknown',
      serverName: json['server_name'] as String?,
      origin: json['origin'] as String?,
      tags: ((json['tags'] as List?) ?? const []).cast<String>(),
      status: issueStatusFrom(json['status'] as String?),
      resolvedCommentId: json['resolved_comment_id'] as String?,
      snapshot: snap == null
          ? const SocialSnapshot()
          : SocialSnapshot.fromJson({
              'specs': snap,
              'mods': const [],
            }),
      commentCount: json['comment_count'] as int? ?? 0,
      isMine: json['is_mine'] == true,
      photos: ((json['photos'] as List?) ?? const []).cast<String>(),
      photoIds: ((json['photo_ids'] as List?) ?? const []).cast<String>(),
      createdAt:
          DateTime.tryParse(json['created_at'] as String? ?? '')?.toLocal(),
      comments: ((json['comments'] as List?) ?? const [])
          .map((c) =>
              SocialIssueComment.fromJson(Map<String, dynamic>.from(c as Map)))
          .toList(),
    );
  }

  SocialIssuePost copyWith({
    List<SocialIssueComment>? comments,
    int? commentCount,
    IssueStatus? status,
    String? resolvedCommentId,
  }) =>
      SocialIssuePost(
        id: id,
        title: title,
        body: body,
        authorDisplayName: authorDisplayName,
        serverName: serverName,
        origin: origin,
        tags: tags,
        status: status ?? this.status,
        resolvedCommentId: resolvedCommentId ?? this.resolvedCommentId,
        snapshot: snapshot,
        commentCount: commentCount ?? this.commentCount,
        isMine: isMine,
        photos: photos,
        photoIds: photoIds,
        createdAt: createdAt,
        comments: comments ?? this.comments,
      );
}

class SocialIssueComment {
  SocialIssueComment({
    required this.id,
    required this.authorDisplayName,
    required this.body,
    this.serverName,
    this.isAnswer = false,
    this.isMine = false,
    this.createdAt,
  });

  final String id;
  final String authorDisplayName;
  final String body;
  final String? serverName;
  final bool isAnswer;
  final bool isMine;
  final DateTime? createdAt;

  factory SocialIssueComment.fromJson(Map<String, dynamic> json) =>
      SocialIssueComment(
        id: json['id'] as String,
        authorDisplayName: json['author_display_name'] as String? ?? 'Unknown',
        serverName: json['server_name'] as String?,
        body: json['body'] as String? ?? '',
        isAnswer: json['is_answer'] == true,
        isMine: json['is_mine'] == true,
        createdAt:
            DateTime.tryParse(json['created_at'] as String? ?? '')?.toLocal(),
      );
}

/// Relative time like "2h ago" — no intl dependency needed on the card.
String socialRelativeTime(DateTime? when) {
  if (when == null) return '';
  final diff = DateTime.now().difference(when);
  if (diff.inMinutes < 1) return 'just now';
  if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
  if (diff.inHours < 24) return '${diff.inHours}h ago';
  if (diff.inDays < 7) return '${diff.inDays}d ago';
  return '${when.day}/${when.month}/${when.year}';
}
