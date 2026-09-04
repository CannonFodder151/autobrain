import 'dart:convert';
import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';

import '../../core/api_client.dart';
import '../../core/offline_cache.dart';

import 'advisor_models.dart';

class AdvisorApi {
  AdvisorApi(this._api);
  final ApiClient _api;

  static String _bodyKey(Map<String, dynamic>? body) {
    if (body == null || body.isEmpty) return '';
    final keys = body.keys.toList()..sort();
    final sorted = <String, dynamic>{for (final k in keys) k: body[k]!};
    final canonical = jsonEncode(sorted);
    return sha256.convert(utf8.encode(canonical)).toString();
  }

  static String cacheKey(String module, String? vehicleId,
      {Map<String, dynamic>? body}) {
    final v = vehicleId ?? '';
    final b = _bodyKey(body);
    return sha256.convert(utf8.encode('advisor:$module:$v:$b')).toString();
  }

  Future<AdvisorResponse> _callWithCache(
    String module,
    String? vehicleId,
    String path, {
    Map<String, String>? query,
    Object? body,
    String? method,
  }) async {
    final m = method ?? (body == null ? 'GET' : 'POST');
    final key = cacheKey(module, vehicleId, body: body as Map<String, dynamic>?);
    final cached = await OfflineCache.instance.get(key);
    AdvisorResponse? cachedResp;
    if (cached != null) {
      try {
        cachedResp = AdvisorResponse.fromJson(
            jsonDecode(cached) as Map<String, dynamic>);
      } catch (e) {
        if (kDebugMode) debugPrint('Advisor cache decode failed: $e');
      }
    }

    try {
      final raw = m == 'GET'
          ? await _api.get(path, query: query)
          : await _api.post(path, body);
      if (raw is Map<String, dynamic>) {
        final resp = AdvisorResponse.fromJson(raw);
        await OfflineCache.instance.put(key, jsonEncode(resp.toJson()));
        return resp;
      }
      if (cachedResp != null) return cachedResp;
      throw ApiException(500, 'Empty response');
    } on ApiException catch (e) {
      if (cachedResp != null) {
        return AdvisorResponse(
          module: cachedResp.module,
          vehicleId: cachedResp.vehicleId,
          generatedAt: cachedResp.generatedAt,
          model: cachedResp.model,
          data: cachedResp.data,
          factors: cachedResp.factors,
        );
      }
      rethrow;
    } catch (_) {
      if (cachedResp != null) return cachedResp;
      rethrow;
    }
  }

  Future<AdvisorResponse> value(String vehicleId) => _callWithCache(
        'value',
        vehicleId,
        '/advisor/value',
        query: {'vehicle_id': vehicleId},
      );

  Future<AdvisorResponse> replace(String vehicleId) => _callWithCache(
        'replace',
        vehicleId,
        '/advisor/replace',
        query: {'vehicle_id': vehicleId},
      );

  Future<AdvisorResponse> upgrade(String vehicleId) => _callWithCache(
        'upgrade',
        vehicleId,
        '/advisor/upgrade',
        query: {'vehicle_id': vehicleId},
      );

  Future<AdvisorResponse> finance(
          String vehicleId, AdvisorFinanceRequest req) =>
      _callWithCache(
        'finance',
        vehicleId,
        '/advisor/finance?vehicle_id=$vehicleId',
        body: req.toJson(),
      );

  Future<AdvisorResponse> dream(
          String vehicleId, AdvisorFinanceRequest req) =>
      _callWithCache(
        'dream',
        vehicleId,
        '/advisor/dream?vehicle_id=$vehicleId',
        body: req.toJson(),
      );

  Future<AdvisorResponse> ai(
          String vehicleId, Map<String, dynamic> tabOutputs) =>
      _callWithCache(
        'ai',
        vehicleId,
        '/advisor/ai?vehicle_id=$vehicleId',
        body: {'tab_outputs': tabOutputs},
      );
}
