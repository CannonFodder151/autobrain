/// GPS unavailable on non-web platforms (mobile uses the native app).
Future<Map<String, double>?> getCurrentPosition() async => null;