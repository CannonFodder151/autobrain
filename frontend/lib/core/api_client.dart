/// HTTP API client with bearer auth and offline queue hooks.
library;

import 'dart:convert';

import 'package:http/http.dart' as http;

import '../core/config.dart';

class ApiException implements Exception {
  final int statusCode;
  final String message;
  ApiException(this.statusCode, this.message);
  @override
  String toString() => message;
}

class ApiClient {
  ApiClient(this._token);
  final String? _token;

  Future<dynamic> get(String path) => _send('GET', path);
  Future<dynamic> post(String path, [Object? body]) => _send('POST', path, body);
  Future<dynamic> patch(String path, [Object? body]) => _send('PATCH', path, body);
  Future<dynamic> delete(String path) => _send('DELETE', path);

  Future<dynamic> upload(String path, List<int> bytes, String filename,
      String contentType) async {
    final uri = Uri.parse('${AppConfig.apiBase}$path');
    final request = http.MultipartRequest('POST', uri)
      ..headers['Authorization'] = 'Bearer $_token'
      ..files.add(http.MultipartFile.fromBytes(
        'file',
        bytes,
        filename: filename,
      ));
    final streamed = await request.send();
    final response = await http.Response.fromStream(streamed);
    return _decode(response);
  }

  Future<dynamic> _send(String method, String path, [Object? body]) async {
    final uri = Uri.parse('${AppConfig.apiBase}$path');
    final headers = {
      'Content-Type': 'application/json',
      if (_token != null) 'Authorization': 'Bearer $_token',
    };
    late http.Response response;
    final encoded = body == null ? null : jsonEncode(body);
    switch (method) {
      case 'GET':
        response = await http.get(uri, headers: headers);
        break;
      case 'DELETE':
        response = await http.delete(uri, headers: headers);
        break;
      case 'POST':
        response = await http.post(uri, headers: headers, body: encoded);
        break;
      case 'PATCH':
        response = await http.patch(uri, headers: headers, body: encoded);
        break;
      default:
        throw ApiException(400, 'Unsupported method');
    }
    return _decode(response);
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
    final response = await http.get(uri, headers: {
      if (_token != null) 'Authorization': 'Bearer $_token',
    });
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return response.bodyBytes;
    }
    throw ApiException(response.statusCode, 'Export failed');
  }
}
