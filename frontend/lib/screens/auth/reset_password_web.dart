// Web implementation: URL fragment clearing requires dart:html which is
// unsupported in Flutter ≥3.22 web builds. Token detection in app.dart reads
// the fragment before navigation; no-op here is safe.
void clearUrlToken() {}
