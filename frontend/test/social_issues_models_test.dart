import 'package:flutter_test/flutter_test.dart';

import 'package:autobrain/community_garage/models.dart';

void main() {
  test('SocialIssuePost.fromJson parses blog list payload (AUT-627)', () {
    final p = SocialIssuePost.fromJson(const {
      'id': 'i1',
      'title': 'Engine won\'t start when hot',
      'body': 'Car cranks but won\'t fire after a long drive.',
      'author_display_name': 'Alice',
      'server_name': 'My Garage',
      'origin': 'local',
      'tags': ['engine', 'starting'],
      'status': 'open',
      'resolved_comment_id': null,
      'vehicle_snapshot': {'make': 'Toyota', 'model': 'Camry', 'year': 2021},
      'comment_count': 2,
      'is_mine': false,
      'created_at': '2026-08-12T00:00:00Z',
    });
    expect(p.id, 'i1');
    expect(p.title, contains('start'));
    expect(p.authorDisplayName, 'Alice');
    expect(p.tags, ['engine', 'starting']);
    expect(p.status, IssueStatus.open);
    expect(p.snapshot.makeModel, 'Toyota Camry');
    expect(p.commentCount, 2);
    expect(p.isMine, isFalse);
  });

  test('SocialIssuePost.fromJson parses photos (AUT-709)', () {
    final p = SocialIssuePost.fromJson(const {
      'id': 'i4',
      'title': 'Brake squeal with pics',
      'body': 'Squeals when cold.',
      'author_display_name': 'Alice',
      'tags': ['brakes'],
      'status': 'open',
      'comment_count': 0,
      'is_mine': true,
      'photos': ['http://assets/p1.webp', 'http://assets/p2.webp'],
      'photo_ids': ['ph1', 'ph2'],
    });
    expect(p.photos, hasLength(2));
    expect(p.photos.first, 'http://assets/p1.webp');
    expect(p.photoIds, ['ph1', 'ph2']);
  });

  test('issueStatusFrom maps all backend statuses', () {
    expect(issueStatusFrom('open'), IssueStatus.open);
    expect(issueStatusFrom('answered'), IssueStatus.answered);
    expect(issueStatusFrom('resolved'), IssueStatus.resolved);
    expect(issueStatusFrom(null), IssueStatus.open);
    expect(issueStatusFrom('weird'), IssueStatus.open);
  });

  test('SocialIssuePost.fromJson parses detail comments', () {
    final p = SocialIssuePost.fromJson(const {
      'id': 'i2',
      'title': 'Rattle at 60km/h',
      'body': 'A rattling noise starts around 60km/h.',
      'author_display_name': 'Bob',
      'tags': ['noise', 'suspension'],
      'status': 'resolved',
      'resolved_comment_id': 'c1',
      'comment_count': 1,
      'is_mine': true,
      'created_at': '2026-08-12T00:00:00Z',
      'comments': [
        {
          'id': 'c1',
          'author_display_name': 'Carol',
          'body': 'Check the sway bar links.',
          'photo': 'http://assets/c1.webp',
          'is_answer': true,
          'is_mine': false,
          'created_at': '2026-08-12T01:00:00Z',
        },
      ],
    });
    expect(p.status, IssueStatus.resolved);
    expect(p.resolvedCommentId, 'c1');
    expect(p.isMine, isTrue);
    expect(p.comments, hasLength(1));
    expect(p.comments.first.isAnswer, isTrue);
    expect(p.comments.first.photo, 'http://assets/c1.webp');
  });

  test('SocialIssueComment parses replies without a photo (AUT-736)', () {
    final c = SocialIssueComment.fromJson(const {
      'id': 'c2',
      'author_display_name': 'Dana',
      'body': 'No picture attached.',
      'photo': null,
      'is_answer': false,
      'is_mine': true,
      'created_at': '2026-08-12T02:00:00Z',
    });
    expect(c.photo, isNull);
  });

  test('issueTagVocabulary matches backend fixed vocabulary', () {
    expect(issueTagVocabulary, contains('engine'));
    expect(issueTagVocabulary, contains('brakes'));
    expect(issueTagVocabulary, contains('electrical'));
    expect(issueTagVocabulary, isNot(contains('gearbox')));
  });

  test('excerpt collapses whitespace', () {
    final p = SocialIssuePost.fromJson(const {
      'id': 'i3',
      'title': 'T',
      'body': 'Line one\n\n   line two\twith tabs',
      'author_display_name': 'A',
      'tags': [],
      'status': 'open',
      'comment_count': 0,
      'is_mine': false,
    });
    expect(p.excerpt, 'Line one line two with tabs');
  });
}
