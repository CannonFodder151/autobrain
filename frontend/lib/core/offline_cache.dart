/// Local SQLite cache for offline mode.
///
/// API responses are cached per key and served when the network is
/// unavailable, then refreshed on reconnect.
library;

import 'package:sqflite/sqflite.dart';
import 'package:path/path.dart' as p;

class OfflineCache {
  OfflineCache._();
  static final OfflineCache instance = OfflineCache._();

  Database? _db;

  Future<Database> _open() async {
    if (_db != null) return _db!;
    final dir = await getDatabasesPath();
    _db = await openDatabase(
      p.join(dir, 'autobrain_cache.db'),
      version: 1,
      onCreate: (db, v) => db.execute(
        'CREATE TABLE cache (key TEXT PRIMARY KEY, body TEXT, saved_at TEXT)',
      ),
    );
    return _db!;
  }

  Future<void> put(String key, String body) async {
    final db = await _open();
    await db.insert(
      'cache',
      {'key': key, 'body': body, 'saved_at': DateTime.now().toIso8601String()},
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<String?> get(String key) async {
    final db = await _open();
    final rows = await db.query('cache', where: 'key = ?', whereArgs: [key]);
    if (rows.isEmpty) return null;
    return rows.first['body'] as String?;
  }

  Future<void> clear() async {
    final db = await _open();
    await db.delete('cache');
  }
}
