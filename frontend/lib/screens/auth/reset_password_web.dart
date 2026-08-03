// Web implementation: clears the ?token= query param from the browser URL.
// ignore_for_file: avoid_web_libraries_in_flutter
import 'dart:html' as html;

void clearUrlToken() {
  if (Uri.base.hasQuery) {
    final clean = Uri.base.replace(queryParameters: {}).toString();
    html.window.history.replaceState(null, '', clean);
  }
}
