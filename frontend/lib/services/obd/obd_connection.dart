/// High-level adapter connection controller for the OBD screen.
///
/// Owns Bluetooth enablement, device discovery (bonded list), the ELM327
/// session lifecycle, and remembering the last adapter so auto-connect works.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter_bluetooth_serial_plus/flutter_bluetooth_serial_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'elm327.dart';
import 'obd_bt_transport.dart';

enum ObdStatus { off, connecting, connected, error }

class ObdAdapter {
  ObdAdapter(this.name, this.address);
  final String name;
  final String address;
  String get label => name.isNotEmpty ? name : address;
}

class ObdConnection extends ChangeNotifier {
  ObdStatus _status = ObdStatus.off;
  ObdStatus get status => _status;

  Elm327Session? _session;
  Elm327Session? get session => _session;

  String? _adapterAddress;
  String? get adapterAddress => _adapterAddress;
  String? get adapterLabel => _adapterLabel;
  String? _adapterLabel;

  String? _error;
  String? get error => _error;

  bool get isConnected => _status == ObdStatus.connected;

  static const prefKey = 'obd_adapter_address';
  static const prefLabelKey = 'obd_adapter_name';

  final _bt = FlutterBluetoothSerial.instance;

  /// Last known adapter, for the auto-connect path.
  Future<ObdAdapter?> lastAdapter() async {
    final prefs = await SharedPreferences.getInstance();
    final address = prefs.getString(prefKey);
    if (address == null) return null;
    return ObdAdapter(prefs.getString(prefLabelKey) ?? '', address);
  }

  Future<List<ObdAdapter>> bondedDevices() async {
    if (!(await _bt.isEnabled ?? false)) {
      await _bt.requestEnable();
    }
    final devices = await _bt.getBondedDevices();
    return devices
        .map((d) => ObdAdapter(d.name ?? '', d.address))
        .toList();
  }

  /// Connects to an adapter and initialises the ELM327 session.
  Future<void> connect(ObdAdapter adapter) async {
    await disconnect();
    _set(ObdStatus.connecting, error: null);
    try {
      final transport = await BluetoothElmTransport.connect(adapter.address);
      final session = Elm327Session(transport);
      await session.init();
      _session = session;
      _adapterAddress = adapter.address;
      _adapterLabel = adapter.label;
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(prefKey, adapter.address);
      await prefs.setString(prefLabelKey, adapter.label);
      _set(ObdStatus.connected);
    } catch (e) {
      await disconnect();
      _set(ObdStatus.error, error: '$e');
    }
  }

  Future<void> disconnect() async {
    try {
      await _session?.close();
    } catch (_) {}
    _session = null;
    if (_status != ObdStatus.off) _set(ObdStatus.off);
  }

  void _set(ObdStatus s, {String? error}) {
    _status = s;
    _error = error;
    notifyListeners();
  }
}

/// Manual "Update VIN" flow: reads the VIN from a connected adapter (mode 09
/// PID 02) and hands it to [save] exactly once. Throws when no session is
/// connected so the UI can prompt the user to connect first.
Future<String> updateVin(
  Elm327Session? session,
  Future<void> Function(String vin) save,
) async {
  if (session == null) throw StateError('OBD adapter not connected');
  final vin = await session.readVin();
  await save(vin);
  return vin;
}
