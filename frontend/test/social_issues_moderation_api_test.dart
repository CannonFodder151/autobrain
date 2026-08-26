import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/community_garage/social_api.dart';
import 'package:autobrain/core/api_client.dart';

class _FakeApi extends ApiClient {
  _FakeApi() : super(null);
  final requests = <String>[];
  final bodies = <Object?>[];
  Object? response;

  @override
  Future<dynamic> get(String path, {Map<String, String>? query}) {
    requests.add('GET $path');
    return Future.value(response);
  }

  @override
  Future<dynamic> post(String path,
      [Object? body, Map<String, String>? headers]) {
    requests.add('POST $path');
    bodies.add(body);
    return Future.value(response);
  }

  @override
  Future<dynamic> delete(String path) {
    requests.add('DELETE $path');
    return Future.value(null);
  }
}

void main() {
  test('issues sends mine=true when My Issues selected (AUT-832)', () async {
    final api = _FakeApi()..response = {'items': [], 'next_cursor': null};
    final social = SocialApi(api);
    await social.issues(mine: true);
    expect(api.requests.single, 'GET /social/issues?limit=20&mine=true');
  });

  test('issues omits mine param by default', () async {
    final api = _FakeApi()..response = {'items': [], 'next_cursor': null};
    final social = SocialApi(api);
    await social.issues();
    expect(api.requests.single, 'GET /social/issues?limit=20');
  });

  test('flagIssueComment posts comment flag with reason (AUT-832)', () async {
    final api = _FakeApi()..response = {'message': 'Flag submitted for review'};
    final social = SocialApi(api);
    await social.flagIssueComment('p1', 'c1', 'Abusive');
    expect(api.requests.single, 'POST /social/issues/p1/comments/c1/flag');
    expect(api.bodies.single, {'reason': 'Abusive'});
  });

  test('reviewQueue GETs the unified moderation hub (AUT-832)', () async {
    final api = _FakeApi()
      ..response = {
        'items': [
          {'kind': 'post', 'post_id': 'p1', 'reason': 'Spam'}
        ]
      };
    final social = SocialApi(api);
    final items = await social.reviewQueue();
    expect(api.requests.single, 'GET /admin/issues/review');
    expect(items.single['post_id'], 'p1');
  });

  test('admin moderation actions hit the admin endpoints (AUT-832)', () async {
    final api = _FakeApi();
    final social = SocialApi(api);
    await social.adminDeletePost('p1');
    await social.adminDeleteComment('c1');
    await social.socialBan('u1');
    await social.socialUnban('u1');
    expect(api.requests, [
      'DELETE /admin/issues/posts/p1',
      'DELETE /admin/issues/comments/c1',
      'POST /admin/users/u1/social-ban',
      'POST /admin/users/u1/social-unban',
    ]);
  });
}
