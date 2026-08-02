/// Cross-platform download + file helpers.
///
/// Uses a browser download on web and temp-file + share on mobile/desktop.
library;

export 'download_io.dart' if (dart.library.html) 'download_web.dart';
