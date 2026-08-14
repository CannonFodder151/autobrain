import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/community_garage/models.dart';
import 'package:autobrain/community_garage/social_api.dart';
import 'package:autobrain/core/api_client.dart';

class _FakeApi extends ApiClient {
  _FakeApi() : super(null);
  final requests = <String>[];
  Object? response;
  Object? lastBody;

  @override
  Future<dynamic> get(String path) {
    requests.add('GET $path');
    return Future.value(response);
  }

  @override
  Future<dynamic> patch(String path, [Object? body]) {
    requests.add('PATCH $path');
    lastBody = body;
    return Future.value(response);
  }
}

void main() {
  test('myPosts hits /social/my-posts and parses items (AUT-501)', () async {
    final api = _FakeApi()
      ..response = {
        'items': [
          {'id': 'b1', 'title': 'Camry build', 'caption': 'Fresh coilovers'}
        ]
      };
    final social = SocialApi(api);
    final posts = await social.myPosts();
    expect(api.requests, ['GET /social/my-posts']);
    expect(posts, hasLength(1));
    expect(posts.single.id, 'b1');
  });

  test('updatePost PATCHes caption and returns updated build', () async {
    final api = _FakeApi()
      ..response = {'id': 'b1', 'title': 'Camry build', 'caption': 'edited'};
    final social = SocialApi(api);
    final updated = await social.updatePost('b1', caption: 'edited');
    expect(api.requests, ['PATCH /social/posts/b1']);
    expect(api.lastBody, {'caption': 'edited'});
    expect(updated.caption, 'edited');
  });

  test('updatePost sends full edit payload (AUT-675)', () async {
    final api = _FakeApi()
      ..response = {
        'id': 'b1',
        'title': 'Renamed',
        'photo_ids': ['p2', 'p1'],
        'share_scope': {'allow_odometer': true}
      };
    final social = SocialApi(api);
    final updated = await social.updatePost(
      'b1',
      title: 'Renamed',
      caption: 'done',
      photoIds: ['p2', 'p1'],
      allowOdometer: true,
    );
    expect(api.lastBody, {
      'title': 'Renamed',
      'caption': 'done',
      'photo_ids': ['p2', 'p1'],
      'share_scope': {'allow_odometer': true},
    });
    expect(updated.photoIds, ['p2', 'p1']);
    expect(updated.shareScope['allow_odometer'], isTrue);
  });

  test('updatePost omits null fields', () async {
    final api = _FakeApi()..response = {'id': 'b1'};
    await SocialApi(api).updatePost('b1', title: null);
    expect(api.lastBody, isEmpty);
  });

  test('updatePost sends empty caption to clear it', () async {
    final api = _FakeApi()..response = {'id': 'b1'};
    await SocialApi(api).updatePost('b1', caption: '');
    expect(api.lastBody, {'caption': ''});
  });
}
