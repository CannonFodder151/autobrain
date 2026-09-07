// Cache layer tests for the mobile offline read-through (AUT-2384).
//
// We test the pure-Dart pieces that don't require Flutter or SQLite:
//   - the per-endpoint TTL lookup
//   - the cache key builder (deterministic + query-ordered)
//
// The SQLite-backed get/put/invalidate paths run on the real device and
// are covered by smoke checks in the app's own startup sequence
// (OfflineCache.clearExpired is called in main.dart).

import 'package:autobrain/core/api_client.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('ApiClient cache key + TTL', () {
    test('cache key is deterministic regardless of map insertion order', () {
      final a = ApiClient.cacheKeyForTest('/vehicles', {'fy': '2024', 'page': '2'});
      final b = ApiClient.cacheKeyForTest('/vehicles', {'page': '2', 'fy': '2024'});
      final c = ApiClient.cacheKeyForTest('/vehicles', <String, String>{});
      expect(a, b);
      expect(a, isNot(c));
      expect(c, '/vehicles');
    });

    test('safe endpoints have a TTL', () {
      expect(ApiClient.ttlForTest('/vehicles'), isNotNull);
      expect(ApiClient.ttlForTest('/vehicles/123'), isNotNull);
      expect(ApiClient.ttlForTest('/vehicles/123/services'), isNotNull);
      expect(ApiClient.ttlForTest('/auth/me'), isNotNull);
      expect(ApiClient.ttlForTest('/social/feed'), isNotNull);
    });

    test('unsafe endpoints have no TTL (never cached)', () {
      expect(ApiClient.ttlForTest('/auth/login'), isNull);
      expect(ApiClient.ttlForTest('/auth/refresh'), isNull);
      expect(ApiClient.ttlForTest('/vehicles/123/services/export'), isNull);
      expect(ApiClient.ttlForTest('/billing/checkout'), isNull);
      expect(ApiClient.ttlForTest('/admin/users'), isNull);
      expect(ApiClient.ttlForTest('/vehicles/123/obd/codes'), isNull);
    });
  });
}
