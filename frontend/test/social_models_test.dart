import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/community_garage/models.dart';

void main() {
  test('SocialBuild.fromJson parses backend feed payload (AUT-332)', () {
    final b = SocialBuild.fromJson(const {
      'id': 'b1',
      'title': 'Camry build',
      'caption': 'Fresh coilovers',
      'author_display_name': 'Alice',
      'server_name': 'My Garage',
      'origin': 'local',
      'snapshot': {
        'title': 'Toyota Camry',
        'vehicle_type': 'car',
        'specs': {'make': 'Toyota', 'model': 'Camry', 'year': 2021},
        'mods': [
          {'name': 'Coilovers', 'category': 'suspension'},
        ],
        'photo_keys': [],
      },
      'photos': ['https://minio/x.webp'],
      'like_count': 3,
      'liked_by_me': true,
      'comment_count': 1,
      'created_at': '2026-08-12T00:00:00Z',
    });
    expect(b.id, 'b1');
    expect(b.snapshot.makeModel, 'Toyota Camry');
    expect(b.snapshot.mods, hasLength(1));
    expect(b.photos, hasLength(1));
    expect(b.likeCount, 3);
    expect(b.likedByMe, isTrue);
    expect(b.isRemote, isFalse);
  });

  test('remote builds flag federated origin', () {
    final b = SocialBuild.fromJson(const {'id': 'r1', 'origin': 'remote'});
    expect(b.isRemote, isTrue);
  });

  test('copyWith preserves feed identity', () {
    final b = SocialBuild.fromJson(const {'id': 'b1', 'like_count': 1});
    final liked = b.copyWith(likedByMe: true, likeCount: 2);
    expect(liked.id, 'b1');
    expect(liked.likedByMe, isTrue);
    expect(liked.likeCount, 2);
  });

  test('SocialComment.fromJson parses comment payload', () {
    final c = SocialComment.fromJson(const {
      'id': 'c1',
      'author_display_name': 'Bob',
      'body': 'Nice build',
      'server_name': 'Other Garage',
      'created_at': '2026-08-12T01:00:00Z',
    });
    expect(c.authorDisplayName, 'Bob');
    expect(c.body, 'Nice build');
    expect(c.serverName, 'Other Garage');
  });

  test('socialScopeFrom maps unknown to server scope', () {
    expect(socialScopeFrom('public'), SocialScope.public);
    expect(socialScopeFrom('friends'), SocialScope.friends);
    expect(socialScopeFrom(null), SocialScope.server);
    expect(socialScopeFrom('weird'), SocialScope.server);
  });
}
