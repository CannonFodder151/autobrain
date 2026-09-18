/// Cross-platform passkey / WebAuthn helper.
///
/// Uses `dart:html` on web (browser-based WebAuthn) and a no-op stub on
/// mobile/desktop. Follows the same pattern as `download.dart` and
/// `geoloc.dart`.
library;

export 'passkey_stub.dart' if (dart.library.html) 'passkey_web.dart';