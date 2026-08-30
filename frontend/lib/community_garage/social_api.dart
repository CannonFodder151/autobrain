/// Community Garage API client — thin mapper over [ApiClient] for the
/// P1 social contract (AUT-332). Screens never touch the wire format.
library;

import 'package:flutter/foundation.dart';

import '../core/api_client.dart';
import 'models.dart';

class SocialSettings {
  SocialSettings({
    this.featureEnabled = true,
    this.federationEnabled = false,
    this.serverName,
    this.serverEmail,
    this.hubStatus,
    this.hubServerId,
    this.hubUrl,
  });

  final bool featureEnabled;
  final bool federationEnabled;
  final String? serverName;
  final String? serverEmail;
  final String? hubStatus;
  final String? hubServerId;
  final String? hubUrl;

  bool get registered => hubStatus == 'registered';

  factory SocialSettings.fromJson(Map<String, dynamic> json) => SocialSettings(
        featureEnabled: json['feature_enabled'] != false,
        federationEnabled: json['federation_enabled'] == true,
        serverName: json['server_name'] as String?,
        serverEmail: json['server_email'] as String?,
        hubStatus: json['hub_status'] as String?,
        hubServerId: json['hub_server_id'] as String?,
        hubUrl: json['hub_url'] as String?,
      );
}

class SocialApi {
  SocialApi(this._api);
  final ApiClient _api;

  /// Homepage feed. Federation on → hub feed; off → local-only (server-side).
  /// Optional `q` filters by title, caption, author or server name.
  Future<List<SocialBuild>> feed({int limit = 20, String? q}) async {
    final qs = q != null && q.trim().isNotEmpty
        ? '&q=${Uri.encodeQueryComponent(q.trim())}'
        : '';
    final data =
        await _api.get('/social/feed?limit=$limit$qs') as Map<String, dynamic>;
    return ((data['items'] as List?) ?? const [])
        .map((e) => SocialBuild.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
  }

  Future<SocialBuild> getPost(String postId) async {
    final data = await _api.get('/social/posts/$postId') as Map<String, dynamic>;
    return SocialBuild.fromJson(data);
  }

  /// The caller's own builds (My Builds tab, AUT-501).
  Future<List<SocialBuild>> myPosts() async {
    final data = await _api.get('/social/my-posts') as Map<String, dynamic>;
    return ((data['items'] as List?) ?? const [])
        .map((e) => SocialBuild.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
  }

  /// Full build edit (AUT-675): rename, reorder/swap photos, adjust scope.
  /// `null` leaves a field unchanged; empty string clears a caption.
  Future<SocialBuild> updatePost(
    String postId, {
    String? title,
    String? caption,
    List<String>? photoIds,
    bool? allowPhotos,
    bool? allowSpecs,
    bool? allowMods,
    bool? allowOdometer,
    bool? allowNotes,
  }) async {
    final body = <String, dynamic>{
      if (title != null) 'title': title,
      if (caption != null) 'caption': caption,
      if (photoIds != null) 'photo_ids': photoIds,
    };
    if (allowPhotos != null ||
        allowSpecs != null ||
        allowMods != null ||
        allowOdometer != null ||
        allowNotes != null) {
      body['share_scope'] = {
        if (allowPhotos != null) 'allow_photos': allowPhotos,
        if (allowSpecs != null) 'allow_specs': allowSpecs,
        if (allowMods != null) 'allow_mods': allowMods,
        if (allowOdometer != null) 'allow_odometer': allowOdometer,
        if (allowNotes != null) 'allow_notes': allowNotes,
      };
    }
    final data =
        await _api.patch('/social/posts/$postId', body) as Map<String, dynamic>;
    return SocialBuild.fromJson(data);
  }

  Future<SocialBuild> createPost({
    required String vehicleId,
    String? title,
    String? caption,
    List<String> photoIds = const [],
    bool allowPhotos = true,
    bool allowSpecs = true,
    bool allowMods = true,
    bool allowOdometer = false,
    bool allowNotes = false,
  }) async {
    final data = await _api.post('/social/posts', {
      'vehicle_id': vehicleId,
      'title': title,
      'caption': caption,
      'photo_ids': photoIds,
      'share_scope': {
        'allow_photos': allowPhotos,
        'allow_specs': allowSpecs,
        'allow_mods': allowMods,
        'allow_odometer': allowOdometer,
        'allow_notes': allowNotes,
      },
    }) as Map<String, dynamic>;
    return SocialBuild.fromJson(data);
  }

  Future<void> deletePost(String postId) => _api.delete('/social/posts/$postId');

  /// Guard fire-and-forget callers: log every failure so silent drops are
  /// visible in dev, then rethrow so screens can still show a SnackBar.
  Future<void> _guarded(Future<void> Function() call, String op) async {
    try {
      await call();
    } catch (e) {
      debugPrint('SocialApi.$op failed: $e');
      rethrow;
    }
  }

  /// Report a build post for review (AUT-896) — kept locally and fanned to
  /// the federation hub's moderation queue.
  Future<void> reportBuild(String postId, String reason) =>
      _guarded(() => _api.post('/social/posts/$postId/report', {'reason': reason}), 'reportBuild');

  Future<SocialBuild> resolveShare(String token) async {
    final data = await _api.get('/social/share/$token') as Map<String, dynamic>;
    return SocialBuild.fromJson(data);
  }

  Future<List<SocialComment>> comments(String postId) async {
    final data =
        await _api.get('/social/posts/$postId/comments') as Map<String, dynamic>;
    return ((data['items'] as List?) ?? const [])
        .map((e) => SocialComment.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
  }

  Future<SocialComment> addComment(String postId, String body) async {
    final data = await _api.post('/social/posts/$postId/comments', {'body': body})
        as Map<String, dynamic>;
    return SocialComment.fromJson(data);
  }

  /// Report a build post (AUT-883 moderation queue).
  Future<void> flagBuild(String postId, String reason) =>
      _guarded(() => _api.post('/social/posts/$postId/flag', {'reason': reason}), 'flagBuild');

  /// Report a comment on a build (AUT-883 moderation queue).
  Future<void> flagBuildComment(String postId, String commentId, String reason) =>
      _guarded(() => _api.post('/social/posts/$postId/comments/$commentId/flag', {'reason': reason}), 'flagBuildComment');

  Future<({bool liked, int count})> toggleLike(String postId) async {
    final data =
        await _api.post('/social/posts/$postId/likes') as Map<String, dynamic>;
    return (liked: data['liked'] == true, count: data['like_count'] as int? ?? 0);
  }

  /// Creates a short share token; `url` is server-relative (origin resolved by
  /// the caller from AppConfig).
  Future<({String token, String url})> createShareLink(String postId) async {
    final data = await _api.post('/social/posts/$postId/share-link')
        as Map<String, dynamic>;
    return (token: data['token'] as String, url: data['url'] as String);
  }

  /// Uploads a photo, returning the media id + display URL.
  Future<({String id, String url})> uploadPhoto(
    List<int> bytes,
    String filename,
    String contentType,
  ) async {
    final data = await _api.upload('/social/uploads', bytes, filename, contentType)
        as Map<String, dynamic>;
    return (id: data['id'] as String, url: data['url'] as String);
  }

  /// Issues Blog browse — reverse-chronological with tag/status/q filters and
  /// keyset cursor pagination (server-side, deterministic). Returns the page
  /// plus `nextCursor` (null when there are no more pages).
  Future<({List<SocialIssuePost> items, String? nextCursor})> issues({
    int limit = 20,
    String? cursor,
    String? tag,
    IssueStatus? status,
    String? q,
    bool mine = false,
  }) async {
    final params = <String>['limit=$limit'];
    if (cursor != null && cursor.isNotEmpty) {
      params.add('cursor=${Uri.encodeQueryComponent(cursor)}');
    }
    if (tag != null && tag.isNotEmpty) {
      params.add('tag=${Uri.encodeQueryComponent(tag)}');
    }
    if (status != null) {
      params.add('status=${status.name}');
    }
    if (q != null && q.trim().isNotEmpty) {
      params.add('q=${Uri.encodeQueryComponent(q.trim())}');
    }
    if (mine) {
      params.add('mine=true');
    }
    final data = await _api.get('/social/issues?${params.join('&')}')
        as Map<String, dynamic>;
    return (
      items: ((data['items'] as List?) ?? const [])
          .map((e) => SocialIssuePost.fromJson(Map<String, dynamic>.from(e as Map)))
          .toList(),
      nextCursor: data['next_cursor'] as String?,
    );
  }

  Future<SocialIssuePost> getIssue(String postId) async {
    final data =
        await _api.get('/social/issues/$postId') as Map<String, dynamic>;
    return SocialIssuePost.fromJson(data);
  }

  Future<SocialIssuePost> createIssue({
    required String title,
    required String body,
    String? vehicleId,
    List<String> photoIds = const [],
  }) async {
    final data = await _api.post('/social/issues', {
      'title': title,
      'body': body,
      if (vehicleId != null) 'vehicle_id': vehicleId,
      if (photoIds.isNotEmpty) 'photo_ids': photoIds,
    }) as Map<String, dynamic>;
    return SocialIssuePost.fromJson(data);
  }

  Future<SocialIssueComment> addIssueComment(
    String postId,
    String body, {
    String? photoId,
  }) async {
    final data = await _api.post('/social/issues/$postId/comments', {
      'body': body,
      if (photoId != null) 'photo_id': photoId,
    }) as Map<String, dynamic>;
    return SocialIssueComment.fromJson(data);
  }

  /// Mark a comment as the answer and resolve the post (author or comment
  /// author only — the server 404s others, so the UI only surfaces it to
  /// eligible commenters).
  Future<void> markAnswer(String postId, String commentId) =>
      _guarded(() => _api.post('/social/issues/$postId/comments/$commentId/answer'), 'markAnswer');

  Future<void> flagIssue(String postId, String reason) =>
      _guarded(() => _api.post('/social/issues/$postId/flag', {'reason': reason}), 'flagIssue');

  Future<void> flagIssueComment(String postId, String commentId, String reason) =>
      _guarded(() => _api.post('/social/issues/$postId/comments/$commentId/flag', {'reason': reason}), 'flagIssueComment');

  Future<void> deleteIssue(String postId) =>
      _api.delete('/social/issues/$postId');

  /// Admin moderation hub (AUT-832): every flagged post and comment.
  Future<List<Map<String, dynamic>>> reviewQueue() async {
    final data = await _api.get('/admin/issues/review') as Map<String, dynamic>;
    return ((data['items'] as List?) ?? const [])
        .map((e) => Map<String, dynamic>.from(e as Map))
        .toList();
  }

  Future<void> adminDeletePost(String postId) =>
      _api.delete('/admin/issues/posts/$postId');

  Future<void> adminDeleteComment(String commentId) =>
      _api.delete('/admin/issues/comments/$commentId');

  /// Admin moderation of reported builds (AUT-883).
  Future<void> adminDeleteBuildPost(String postId) =>
      _api.delete('/admin/social/posts/$postId');

  Future<void> adminDeleteBuildComment(String commentId) =>
      _api.delete('/admin/social/comments/$commentId');

  Future<void> socialBan(String userId) =>
      _api.post('/admin/users/$userId/social-ban');

  Future<void> socialUnban(String userId) =>
      _api.post('/admin/users/$userId/social-unban');

  /// Admin toggles (GET/PATCH /admin/social).
  Future<SocialSettings> settings() async {
    final data = await _api.get('/admin/social') as Map<String, dynamic>;
    return SocialSettings.fromJson(data);
  }

  Future<SocialSettings> updateSettings({
    bool? featureEnabled,
    bool? federationEnabled,
    String? serverName,
    String? serverEmail,
  }) async {
    final data = await _api.patch('/admin/social', {
      if (featureEnabled != null) 'feature_enabled': featureEnabled,
      if (federationEnabled != null) 'federation_enabled': federationEnabled,
      if (serverName != null) 'server_name': serverName,
      if (serverEmail != null) 'server_email': serverEmail,
    }) as Map<String, dynamic>;
    return SocialSettings.fromJson(data);
  }

  Future<Map<String, dynamic>> registerWithHub() async =>
      (await _api.post('/admin/social/register')) as Map<String, dynamic>;

  Future<void> unregisterFromHub() => _api.post('/admin/social/unregister');
}
