/// Community Garage API client — thin mapper over [ApiClient] for the
/// P1 social contract (AUT-332). Screens never touch the wire format.
library;

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
  Future<List<SocialBuild>> feed({int limit = 20}) async {
    final data = await _api.get('/social/feed?limit=$limit') as Map<String, dynamic>;
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

  Future<SocialBuild> updatePost(String postId, {String? caption}) async {
    final data = await _api.patch('/social/posts/$postId', {'caption': caption})
        as Map<String, dynamic>;
    return SocialBuild.fromJson(data);
  }

  Future<SocialBuild> createPost({
    required String vehicleId,
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
