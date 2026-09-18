/// Web implementation of PassKey / WebAuthn using `dart:html`.
///
/// Calls `navigator.credentials.create()` and `navigator.credentials.get()`
/// for the WebAuthn ceremony. Returns plain Dart maps that the backend
/// expects (base64url-encoded strings).
library;

import 'dart:async';
import 'dart:convert';
import 'dart:html' as html;
import 'dart:js' as js;
import 'dart:typed_data';

import 'package:flutter/foundation.dart';

/// Base64url encode bytes → string (no padding).
String _bytesToB64url(List<int> bytes) {
  return base64Url.encode(bytes).replaceAll('=', '');
}

/// Base64url decode string → bytes.
List<int> _b64urlToBytes(String b64) {
  final padded = b64 + '=' * ((4 - b64.length % 4) % 4);
  return base64Url.decode(padded);
}

/// Convert a JS object to a Dart map recursively.
Map<String, dynamic> _jsObjToMap(js.JsObject obj) {
  final result = <String, dynamic>{};
  final keys = _objectKeys(obj);
  for (var i = 0; i < keys.length; i++) {
    final key = keys[i].toDart;
    final val = _getProperty(obj, key.toJS);
    result[key] = _jsValToDart(val);
  }
  return result;
}

dynamic _jsValToDart(js.JsObject? val) {
  if (val == null) return null;
  if (val.isString) return val.toString();
  if (val.isNumber) return val.toDouble();
  if (val.isBool) return val.toBool();
  if (val.isArray) {
    final arr = val;
    final list = <dynamic>[];
    for (var i = 0; i < arr.length; i++) {
      list.add(_jsValToDart(arr[i]));
    }
    return list;
  }
  if (val.isObject) return _jsObjToMap(val);
  return val.toString();
}

@JS('Object.keys')
external List<String> _objectKeys(js.JsObject obj);

@JS('Object.getOwnPropertyDescriptor')
external js.JsObject? _getPropertyDescriptor(js.JsObject obj, String key);

dynamic _getProperty(js.JsObject obj, String key) {
  final desc = _getPropertyDescriptor(obj, key);
  if (desc == null) return null;
  return desc['value'];
}

/// Check if the browser supports WebAuthn.
bool get webAuthnSupported {
  if (!kIsWeb) return false;
  try {
    return html.window.navigator.credentials != null;
  } catch (_) {
    return false;
  }
}

/// Start a PassKey registration ceremony.
///
/// Calls `navigator.credentials.create()` with the provided options.
/// Returns a map with: id, rawId, response (attestationObject, clientDataJSON),
/// type — all base64url strings, matching the backend's expected schema.
Future<Map<String, dynamic>?> startRegistration(
  Map<String, dynamic> options,
) async {
  if (!kIsWeb) throw UnsupportedError('PassKey registration is only supported on web');

  final publicKey = _buildCreateOptions(options);
  final credPromise = html.window.navigator.credentials?.create(publicKey);
  if (credPromise == null) return null;

  final cred = await _awaitPromise(credPromise);
  if (cred == null) return null;

  return _parseCredential(cred);
}

/// Start a PassKey authentication ceremony.
///
/// Calls `navigator.credentials.get()` with the provided options.
/// Returns a map with: id, rawId, response (authenticatorData, clientDataJSON,
/// signature, userHandle), type — all base64url strings.
Future<Map<String, dynamic>?> startAuthentication(
  Map<String, dynamic> options,
) async {
  if (!kIsWeb) throw UnsupportedError('PassKey authentication is only supported on web');

  final publicKey = _buildGetOptions(options);
  final credPromise = html.window.navigator.credentials?.get(publicKey);
  if (credPromise == null) return null;

  final cred = await _awaitPromise(credPromise);
  if (cred == null) return null;

  return _parseCredential(cred);
}

Map<String, dynamic> _parseCredential(js.JsObject cred) {
  final id = _getProperty(cred, 'id') as String?;
  final rawId = _getProperty(cred, 'rawId') as String?;
  final type = _getProperty(cred, 'type') as String?;
  final responseObj = _getProperty(cred, 'response') as js.JsObject?;

  Map<String, dynamic>? response;
  if (responseObj != null) {
    response = _jsObjToMap(responseObj);
    // Convert ArrayBuffer fields to base64url strings.
    for (final key in ['attestationObject', 'clientDataJSON', 'authenticatorData', 'signature', 'userHandle']) {
      if (response[key] is Uint8List) {
        response[key] = _bytesToB64url(response[key]);
      }
    }
  }

  return {
    'id': id,
    'rawId': rawId,
    'type': type,
    'response': response ?? {},
  };
}

// ---------------------------------------------------------------------------
// Build PublicKeyCredentialCreationOptions / RequestOptions as JS objects
// ---------------------------------------------------------------------------

js.JsObject _buildCreateOptions(Map<String, dynamic> opts) {
  // publicKey: { rp, user, challenge, pubKeyCredParams, timeout, excludeCredentials, attestation }
  final publicKey = js.JsObject.jsify({
    'rp': _jsifyMap(opts['rp'] as Map<String, dynamic>),
    'user': _jsifyUser(opts['user'] as Map<String, dynamic>),
    'challenge': _b64urlToBytes(opts['challenge'] as String),
    'pubKeyCredParams': _jsifyList(opts['pubKeyCredParams'] as List),
    'timeout': opts['timeout'] as int? ?? 60000,
    'excludeCredentials': _jsifyList(opts['excludeCredentials'] as List? ?? []),
    'attestation': opts['attestation'] as String? ?? 'none',
  });

  return js.JsObject.jsify({'publicKey': publicKey});
}

js.JsObject _buildGetOptions(Map<String, dynamic> opts) {
  final publicKey = js.JsObject.jsify({
    'challenge': _b64urlToBytes(opts['challenge'] as String),
    'timeout': opts['timeout'] as int? ?? 60000,
    'rpId': opts['rpId'] as String,
    'allowCredentials': _jsifyList(opts['allowCredentials'] as List),
    'userVerification': opts['userVerification'] as String? ?? 'preferred',
  });

  return js.JsObject.jsify({'publicKey': publicKey});
}

js.JsObject _jsifyMap(Map<String, dynamic> map) {
  return js.JsObject.jsify(map);
}

js.JsObject _jsifyUser(Map<String, dynamic> user) {
  return js.JsObject.jsify({
    'id': _b64urlToBytes(user['id'] as String),
    'name': user['name'] as String,
    'displayName': user['displayName'] as String,
  });
}

js.JsArray _jsifyList(List list) {
  final result = js.JsArray();
  for (final item in list) {
    if (item is Map) {
      result.add(_jsifyMap(item));
    } else {
      result.add(item);
    }
  }
  return result;
}

// ---------------------------------------------------------------------------
// Promise await helper
// ---------------------------------------------------------------------------

Future<js.JsObject?> _awaitPromise(html.JSPromise promise) {
  final completer = Completer<js.JsObject?>();

  promise.then(
    (value) {
      if (value is js.JsObject) {
        completer.complete(value);
      } else {
        completer.complete(null);
      }
    },
    onError: (error) {
      completer.completeError(error);
    },
  );

  return completer.future;
}