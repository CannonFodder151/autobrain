// Web implementation: clears the #token= fragment from the browser URL.
// ignore_for_file: avoid_web_libraries_in_flutter
import 'dart:html' as html;

void clearUrlToken() {
  final uri = Uri.base;
  if (uri.fragment.contains('token=')) {
    final clean = uri.replace(fragment: '').toString();
    html.window.history.replaceState(null, '', clean);
  } else if (uri.hasQuery) {
    // legacy: clear ?token= query param
    final clean = uri.replace(queryParameters: {}).toString();
    html.window.history.replaceState(null, '', clean);
  }
}
