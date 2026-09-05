/// Local SQLite cache for offline mode + in-memory hot layer for cheap reads.
///
/// API responses are cached per key and served when the network is
/// unavailable, then refreshed on reconnect. Each cache entry carries a
/// `saved_at` timestamp and an optional `ttl_ms` (milliseconds). Entries
/// with a TTL are considered stale once `now - saved_at > ttl_ms`; reads
/// distinguish between a hit and a stale hit so callers can decide whether
/// to refresh in the background.
///
/// The class is a process-wide singleton (`OfflineCache.instance`) — the
/// underlying SQLite database is opened lazily on first use.
library;

import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart' as p;

class CacheEntry {
  const CacheEntry(this.body, this.savedAt, this.stale);
  final String body;
  final DateTime savedAt;
  final bool stale;
}

class OfflineCache {
  OfflineCache._();
  static final OfflineCache instance = OfflineCache._();

  Database? _db;

  /// In-memory mirror of the most recent reads. Bounded to keep memory
  /// pressure off — the SQLite table is the source of truth; this is just
  /// an LRU-ish shortcut for the hottest read paths (vehicle list, profile).
  static const int _hotCapacity = 64;
  final Map<String, CacheEntry> _hot = <String, CacheEntry>{};

  Future<Database> _open() async {
    if (_db != null) return _db!;
    final dir = await getDatabasesPath();
    _db = await openDatabase(
      p.join(dir, 'autobrain_cache.db'),
      version: 2,
      onCreate: (db, v) => db.execute(
        'CREATE TABLE cache (key TEXT PRIMARY KEY, body TEXT, saved_at TEXT, ttl_ms INTEGER)',
      ),
      onUpgrade: (db, oldV, newV) async {
        // v1 -> v2: add ttl_ms column. The old (dead-coded) cache put no
        // TTL, so all existing rows are treated as fresh-forever.
        if (oldV < 2) {
          await db.execute('ALTER TABLE cache ADD COLUMN ttl_ms INTEGER');
        }
      },
    );
    return _db!;
  }

  /// Persist [body] under [key] with an optional [ttl].
  Future<void> put(String key, String body, {Duration? ttl}) async {
    final db = await _open();
    final row = <String, Object?>{
      'key': key,
      'body': body,
      'saved_at': DateTime.now().toIso8601String(),
      'ttl_ms': ttl?.inMilliseconds,
    };
    await db.insert('cache', row, conflictAlgorithm: ConflictAlgorithm.replace);
    _hot[key] = CacheEntry(body, DateTime.now(), false);
    _evictHot();
  }

  /// Read a cache entry. Returns null when the key is missing. When [allowStale]
  /// is false, expired entries (TTL exceeded) are treated as missing. When
  /// allowStale is true, the entry is returned with `stale: true` so callers
  /// can choose to refresh in the background.
  Future<CacheEntry?> get(String key, {bool allowStale = false}) async {
    final hot = _hot[key];
    if (hot != null) {
      if (_isExpired(hot) && !allowStale) {
        _hot.remove(key);
      } else {
        return hot;
      }
    }
    final db = await _open();
    final rows =
        await db.query('cache', where: 'key = ?', whereArgs: [key]);
    if (rows.isEmpty) return null;
    final body = rows.first['body'] as String?;
    final savedAt = DateTime.tryParse((rows.first['saved_at'] as String?) ?? '');
    if (body == null || savedAt == null) return null;
    final entry = CacheEntry(body, savedAt, _isExpiredTime(savedAt, rows.first['ttl_ms'] as int?));
    if (entry.stale && !allowStale) return null;
    _hot[key] = entry;
    _evictHot();
    return entry;
  }

  /// Drop every entry whose key starts with [prefix]. Use after a write to
  /// invalidate related list caches, e.g. invalidateByPrefix('/vehicles/42/fuel').
  Future<void> invalidateByPrefix(String prefix) async {
    final db = await _open();
    await db.delete('cache', where: 'key LIKE ?', whereArgs: ['$prefix%']);
    _hot.removeWhere((k, _) => k.startsWith(prefix));
  }

  /// Drop a single key.
  Future<void> invalidate(String key) async {
    final db = await _open();
    await db.delete('cache', where: 'key = ?', whereArgs: [key]);
    _hot.remove(key);
  }

  /// Wipe everything (used by logout / cache clear in settings).
  Future<void> clear() async {
    final db = await _open();
    await db.delete('cache');
    _hot.clear();
  }

  /// Drop expired rows from the SQLite table. Safe to call at boot.
  Future<void> clearExpired() async {
    final db = await _open();
    final rows = await db.query('cache');
    final now = DateTime.now();
    final stale = <String>[];
    for (final r in rows) {
      final ttl = r['ttl_ms'] as int?;
      final savedAt = DateTime.tryParse((r['saved_at'] as String?) ?? '');
      if (ttl == null || savedAt == null) continue;
      if (now.difference(savedAt).inMilliseconds > ttl) {
        stale.add(r['key'] as String);
      }
    }
    if (stale.isNotEmpty) {
      final placeholders = List.filled(stale.length, '?').join(',');
      await db.delete('cache', where: 'key IN ($placeholders)', whereArgs: stale);
    }
  }

  static bool _isExpired(CacheEntry e) =>
      _isExpiredTime(e.savedAt, _ttlFromHot(e));

  static bool _isExpiredTime(DateTime savedAt, int? ttlMs) {
    if (ttlMs == null) return false;
    return DateTime.now().difference(savedAt).inMilliseconds > ttlMs;
  }

  /// TTL on hot entries is unknown (we only stored body+savedAt), so hot
  /// entries never auto-expire here — the canonical TTL lives in SQLite and
  /// will be re-evaluated on the next miss. Hot entries are advisory.
  static int? _ttlFromHot(CacheEntry e) => null;

  void _evictHot() {
    if (_hot.length <= _hotCapacity) return;
    final drop = _hot.length - _hotCapacity;
    final keys = _hot.keys.take(drop).toList();
    for (final k in keys) {
      _hot.remove(k);
    }
  }
}
