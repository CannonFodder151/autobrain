import 'dart:io';

import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

/// Save bytes to a temp file and open the platform share sheet.
Future<void> downloadBytes(String filename, List<int> bytes) async {
  final dir = await getTemporaryDirectory();
  final file = File('${dir.path}/$filename');
  await file.writeAsBytes(bytes);
  await Share.shareXFiles([XFile(file.path)]);
}

/// Read a file from disk (io only).
Future<List<int>> readLocalFile(String path) async {
  return File(path).readAsBytes();
}
