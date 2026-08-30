import 'dart:convert';
import 'dart:html' as html;
import 'dart:typed_data';

/// Trigger a browser download for the given bytes.
Future<void> downloadBytes(String filename, List<int> bytes) async {
  final blob = html.Blob([Uint8List.fromList(bytes)]);
  final url = html.Url.createObjectUrlFromBlob(blob);
  final anchor = html.AnchorElement(href: url)
    ..download = filename
    ..click();
  html.Url.revokeObjectUrl(url);
}

/// Not supported on web — web pickers expose bytes directly.
Future<List<int>> readLocalFile(String path) async {
  throw UnsupportedError('readLocalFile is not available on web');
}
