/// Bluetooth Classic SPP transport for ELM327 adapters (e.g. VGate iCar Pro).
///
/// Sends `command\r` and returns everything up to the ELM327 `>` prompt.
/// Android-only today — iOS has no public Bluetooth Classic; a BLE ELM327
/// (UART GATT) transport is the iOS follow-up (`ponytail: iOS BLE transport,
/// add when an iPhone build is on the roadmap`).
library;

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_bluetooth_serial_plus/flutter_bluetooth_serial_plus.dart';

import 'elm327.dart';

class BluetoothElmTransport implements Elm327Transport {
  BluetoothElmTransport._(this._connection);

  final BluetoothConnection _connection;
  final StringBuffer _inbox = StringBuffer();
  Completer<String>? _pending;
  StreamSubscription<Uint8List>? _sub;

  /// Opens an SPP socket to a bonded device and starts reading.
  static Future<BluetoothElmTransport> connect(String address) async {
    final conn = await BluetoothConnection.toAddress(address);
    final t = BluetoothElmTransport._(conn);
    await t._listen();
    return t;
  }

  Future<void> _listen() async {
    _sub = _connection.input.listen((bytes) {
      _inbox.write(ascii.decode(bytes, allowInvalid: true));
      final text = _inbox.toString();
      final idx = text.indexOf('>');
      if (idx < 0) return;
      final reply = text.substring(0, idx);
      _inbox.clear();
      _pending?.complete(reply);
    });
  }

  @override
  Future<String> send(String cmd) async {
    if (!_connection.isConnected) {
      throw Elm327Exception('Bluetooth adapter is disconnected');
    }
    final completer = _pending = Completer<String>();
    _connection.output.add(ascii.encode('$cmd\r'));
    try {
      final reply = await completer.future
          .timeout(const Duration(seconds: 6));
      if (reply.trim() == '?') {
        throw Elm327Exception('Adapter rejected "$cmd"');
      }
      return reply;
    } on TimeoutException {
      throw Elm327Exception('Timeout waiting for reply to "$cmd"');
    } finally {
      _pending = null;
    }
  }

  @override
  bool get isConnected => _connection.isConnected;

  @override
  Future<void> close() async {
    await _sub?.cancel();
    await _connection.close();
  }
}
