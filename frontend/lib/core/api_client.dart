/// HTTP API client with bearer auth and offline queue hooks.
library;

import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';

import '../core/config.dart';

/// Resolve a safe multipart content type. Empty/unparseable values (e.g. the
/// empty string `XFile.mimeType` returns for HEIC) fall back to a
/// filename-derived MIME, then to octet-stream, so `MediaType.parse` never
/// throws (AUT-796).
MediaType safeContentType(String contentType, String filename) {
  final trimmed = contentType.trim();
  if (trimmed.isNotEmpty) {
    try {
      return MediaType.parse(trimmed);
    } catch (_) {}
  }
  return MediaType.parse(mimeForFile(filename));
}

/// Best-effort MIME guess from a filename extension (upload helper).
String mimeForFile(String filename,
    [String fallback = 'application/octet-stream']) {
  final ext =
      filename.contains('.') ? filename.split('.').last.toLowerCase() : '';
  switch (ext) {
    case 'pdf':
      return 'application/pdf';
    case 'jpg':
    case 'jpeg':
      return 'image/jpeg';
    case 'png':
      return 'image/png';
    case 'webp':
      return 'image/webp';
    case 'heic':
    case 'heif':
      return 'image/heic';
    case 'tiff':
    case 'tif':
      return 'image/tiff';
    default:
      return fallback;
  }
}

class ApiException implements Exception {
  final int statusCode;
  final String message;
  ApiException(this.statusCode, this.message);
  @override
  String toString() => message;
}

class ApiClient {
  /// [onRefresh] returns a fresh access token (or null if refresh fails).
  /// Invoked once when a request comes back 401; the request is then retried.
  ApiClient(String? token, {this.onRefresh}) : _token = token;
  String? _token;
  final Future<String?> Function()? onRefresh;
  static const Duration _timeout = Duration(seconds: 30);
  Future<String?>? _inflightRefresh;

  Future<dynamic> get(String path, {Map<String, String>? query}) =>
      _send('GET', path, null, null, query);
  Future<dynamic> post(String path,
          [Object? body, Map<String, String>? headers]) =>
      _send('POST', path, body, headers);
  Future<dynamic> patch(String path, [Object? body]) =>
      _send('PATCH', path, body);
  Future<dynamic> put(String path, [Object? body]) => _send('PUT', path, body);
  Future<dynamic> delete(String path) => _send('DELETE', path);

  Future<dynamic> upload(
      String path, List<int> bytes, String filename, String contentType) async {
    final uri = Uri.parse('${AppConfig.apiBase}$path');
    final request = http.MultipartRequest('POST', uri)
      ..headers['Authorization'] = 'Bearer $_token'
      ..files.add(http.MultipartFile.fromBytes(
        'file',
        bytes,
        filename: filename,
        contentType: safeContentType(contentType, filename),
      ));
    final streamed = await request.send().timeout(_timeout);
    final response = await http.Response.fromStream(streamed).timeout(_timeout);
    if (response.statusCode == 401 && _token != null && onRefresh != null) {
      final newToken = await _refresh();
      if (newToken != null) {
        _token = newToken;
        final retry = http.MultipartRequest('POST', uri)
          ..headers['Authorization'] = 'Bearer $_token'
          ..files.add(http.MultipartFile.fromBytes(
            'file',
            bytes,
            filename: filename,
            contentType: safeContentType(contentType, filename),
          ));
        final retried = await retry.send().timeout(_timeout);
        return _decode(
            await http.Response.fromStream(retried).timeout(_timeout));
      }
    }
    return _decode(response);
  }

  Future<dynamic> _send(String method, String path,
      [Object? body,
      Map<String, String>? extraHeaders,
      Map<String, String>? query]) async {
    final parsed = Uri.parse('${AppConfig.apiBase}$path');
    // Only override query params when explicitly supplied; otherwise preserve
    // any query already present in [path] (callers like social_api embed it).
    final uri = query == null ? parsed : parsed.replace(queryParameters: query);
    final headers = {
      'Content-Type': 'application/json',
      if (_token != null) 'Authorization': 'Bearer $_token',
      ...?extraHeaders,
    };
    var response = await _raw(method, uri, headers, body);
    if (response.statusCode == 401 && _token != null && onRefresh != null) {
      final newToken = await _refresh();
      if (newToken != null) {
        _token = newToken;
        headers['Authorization'] = 'Bearer $_token';
        response = await _raw(method, uri, headers, body);
      }
    }
    return _decode(response);
  }

  Future<http.Response> _raw(
      String method, Uri uri, Map<String, String> headers, Object? body) {
    final encoded = body == null ? null : jsonEncode(body);
    switch (method) {
      case 'GET':
        return http.get(uri, headers: headers).timeout(_timeout);
      case 'DELETE':
        return http.delete(uri, headers: headers).timeout(_timeout);
      case 'POST':
        return http
            .post(uri, headers: headers, body: encoded)
            .timeout(_timeout);
      case 'PATCH':
        return http
            .patch(uri, headers: headers, body: encoded)
            .timeout(_timeout);
      case 'PUT':
        return http.put(uri, headers: headers, body: encoded).timeout(_timeout);
      default:
        throw ApiException(400, 'Unsupported method');
    }
  }

  /// Single in-flight refresh: concurrent 401s share one refresh call.
  Future<String?> _refresh() {
    return _inflightRefresh ??=
        onRefresh!().whenComplete(() => _inflightRefresh = null);
  }

  dynamic _decode(http.Response response) {
    if (response.statusCode >= 200 && response.statusCode < 300) {
      if (response.body.isEmpty) return null;
      return jsonDecode(response.body);
    }
    String message = 'Request failed (${response.statusCode})';
    try {
      final data = jsonDecode(response.body);
      if (data is Map && data['detail'] != null) {
        message = data['detail'].toString();
      }
    } catch (_) {}
    throw ApiException(response.statusCode, message);
  }

  /// Download a raw byte payload (e.g. PDF/CSV export).
  Future<List<int>> export(String path) async {
    final uri = Uri.parse('${AppConfig.apiBase}$path');
    var headers = {if (_token != null) 'Authorization': 'Bearer $_token'};
    var response = await http.get(uri, headers: headers).timeout(_timeout);
    if (response.statusCode == 401 && _token != null && onRefresh != null) {
      final newToken = await _refresh();
      if (newToken != null) {
        _token = newToken;
        headers = {'Authorization': 'Bearer $_token'};
        response = await http.get(uri, headers: headers).timeout(_timeout);
      }
    }
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return response.bodyBytes;
    }
    throw ApiException(response.statusCode, 'Export failed');
  }
}
