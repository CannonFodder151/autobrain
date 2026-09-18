/// Stub implementation for non-web platforms.
///
/// PassKey/WebAuthn is only supported on web. On mobile/desktop, these
/// functions throw [UnsupportedError].

bool get webAuthnSupported => false;

Future<Map<String, dynamic>?> startRegistration(
  Map<String, dynamic> options,
) async {
  throw UnsupportedError(
    'PassKey registration is only supported on web',
  );
}

Future<Map<String, dynamic>?> startAuthentication(
  Map<String, dynamic> options,
) async {
  throw UnsupportedError(
    'PassKey authentication is only supported on web',
  );
}