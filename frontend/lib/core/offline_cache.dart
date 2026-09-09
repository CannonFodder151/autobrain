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

import 'dart:async';
import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart' as p;

class CacheEntry {
  const CacheEntry(this.body, this.savedAt, this.stale, this.ttlMs);
  final String body;
  final DateTime savedAt;
  final bool stale;
  final int? ttlMs;
}

class OfflineCache {
  OfflineCache._();
  static final OfflineCache instance = OfflineCache._();

  Database? _db;
  Future<void>? _opening;

  /// In-memory mirror of the most recent reads. Bounded to keep memory
  /// pressure off — the SQLite table is the source of truth; this is just
  /// an LRU-ish shortcut for the hottest read paths (vehicle list, profile).
  static const int _hotCapacity = 64;
  final Map<String, CacheEntry> _hot = <String, CacheEntry>{};

  /// Ultra-hot in-memory layer for the busiest endpoints (vehicles, profile).
  /// These entries bypass SQLite entirely and expire after [ultraHotTtl]
  /// (default 10 s). Only a handful of keys are ever stored here.
  static const Duration ultraHotTtl = Duration(seconds: 10);
  final Map<String, CacheEntry> _ultraHot = <String, CacheEntry>{};

  Future<Database> _open() async {
    if (_db != null) return _db!;
    if (_opening != null) return await _opening!;
    _opening = _openImpl().then((d) {
      _db = d;
      _opening = null;
      return d;
    }).catchError((e) {
      _opening = null;
      throw e;
    });
    try {
      return await _opening!;
    } on Exception {
      _opening = null;
      rethrow;
    }
  }

  Future<Database> _openImpl() async {
    final dir = await getDatabasesPath();
    _db = await openDatabase(
      p.join(dir, 'autobrain_cache.db'),
      version: 2,
      onCreate: (db, v) => db.execute(
        'CREATE TABLE cache (key TEXT PRIMARY KEY, body TEXT, saved_at TEXT, ttl_ms INTEGER)',
      ),
      onUpgrade: (db, oldV, newV) async {
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
    _hot[key] = CacheEntry(body, DateTime.now(), false, ttl?.inMilliseconds);
    _evictHot();
  }

  /// Read a cache entry. Returns null when the key is missing. When [allowStale]
  /// is false, expired entries (TTL exceeded) are treated as missing. When
  /// allowStale is true, the entry is returned with `stale: true` so callers
  /// can choose to refresh in the background.
  ///
  /// Check order: ultra-hot (in-memory, 10 s) → hot (in-memory LRU) → SQLite.
  Future<CacheEntry?> get(String key, {bool allowStale = false}) async {
    // Ultra-hot in-memory layer: fastest possible read, no SQLite involved.
    final ultra = _ultraHot[key];
    if (ultra != null) {
      if (_isExpired(ultra)) {
        _ultraHot.remove(key);
      } else {
        return ultra;
      }
    }
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
    final ttlMs = rows.first['ttl_ms'] as int?;
    final entry = CacheEntry(body, savedAt, _isExpiredTime(savedAt, ttlMs), ttlMs);
    if (entry.stale && !allowStale) return null;
    _hot[key] = entry;
    _evictHot();
    return entry;
  }

  /// Drop every entry whose key starts with [prefix].
  Future<void> invalidateByPrefix(String prefix) async {
    final db = await _open();
    await db.delete('cache', where: 'key LIKE ?', whereArgs: ['$prefix%']);
    _hot.removeWhere((k, _) => k.startsWith(prefix));
    _ultraHot.removeWhere((k, _) => k.startsWith(prefix));
  }

  /// Drop a single key.
  Future<void> invalidate(String key) async {
    final db = await _open();
    await db.delete('cache', where: 'key = ?', whereArgs: [key]);
    _hot.remove(key);
    _ultraHot.remove(key);
  }

  /// Wipe everything (used by logout / cache clear in settings).
  Future<void> clear() async {
    final db = await _open();
    await db.delete('cache');
    _hot.clear();
    _ultraHot.clear();
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
      _isExpiredTime(e.savedAt, e.ttlMs);

  static bool _isExpiredTime(DateTime savedAt, int? ttlMs) {
    if (ttlMs == null) return false;
    return DateTime.now().difference(savedAt).inMilliseconds > ttlMs;
  }

  void _evictHot() {
    if (_hot.length <= _hotCapacity) return;
    final drop = _hot.length - _hotCapacity;
    final keys = _hot.keys.take(drop).toList();
    for (final k in keys) {
      _hot.remove(k);
    }
  }

  /// Read-only ultra-hot lookup. Returns the entry only when it is still
  /// fresh (within [ultraHotTtl]). Never touches SQLite.
  CacheEntry? getUltraHot(String key) {
    final e = _ultraHot[key];
    if (e == null) return null;
    if (_isExpired(e)) {
      _ultraHot.remove(key);
      return null;
    }
    return e;
  }

  /// Store an entry in the ultra-hot layer (in-memory only).
  void putUltraHot(String key, String body) {
    _ultraHot[key] = CacheEntry(
        body, DateTime.now(), false, ultraHotTtl.inMilliseconds);
  }

  /// Drop a single ultra-hot key.
  void invalidateUltraHot(String key) => _ultraHot.remove(key);
}
