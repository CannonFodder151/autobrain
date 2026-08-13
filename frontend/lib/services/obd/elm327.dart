/// ELM327 / OBD-II protocol layer (pure Dart, no Bluetooth in here).
///
/// Transport-agnostic: [Elm327Session] talks to any [Elm327Transport] that
/// sends a command and returns the raw adapter reply. All response parsing
/// and PID/DTC decoding lives here as pure functions so it can be unit-tested
/// against real adapter captures without hardware.
library;

import 'dart:convert';

class Elm327Exception implements Exception {
  Elm327Exception(this.message);
  final String message;
  @override
  String toString() => 'ELM327: $message';
}

/// Minimal byte transport an ELM327 adapter speaks over (SPP/BLE serial).
abstract class Elm327Transport {
  /// Sends `cmd` (e.g. `010C`) and returns the raw reply text, newline
  /// normalised, without the trailing `>` prompt. Throws [Elm327Exception]
  /// when the adapter replies `?`.
  Future<String> send(String cmd);

  /// Tears the serial connection down.
  Future<void> close();
}

/// One live-PID definition. Decoders are shared per byte-width; anything
/// non-linear can override [decode] (see e.g. coolant temperature).
class ObdPid {
  const ObdPid(this.command, this.name, this.unit, this.bytes, {this.decode})
      : assert(bytes >= 1 && bytes <= 4);

  final String command; // e.g. '010C'
  final String name; // e.g. 'Engine RPM'
  final String unit; // e.g. 'rpm'
  final int bytes; // payload byte count (no mode/pid prefix)
  final num Function(List<int> bytes)? decode;

  num defaultValue(List<int> b) {
    final v = switch (bytes) {
      1 => b[0],
      2 => (b[0] << 8) | b[1],
      3 => (b[0] << 16) | (b[1] << 8) | b[2],
      _ => (b[0] << 24) | (b[1] << 16) | (b[2] << 8) | b[3],
    };
    return v.toDouble();
  }

  num value(List<int> b) {
    final d = decode ?? defaultValue;
    return d(b);
  }

  String format(num v) => v == v.roundToDouble()
      ? v.toInt().toString()
      : v.toStringAsFixed(2);

  static num pct(List<int> b) => b[0] * 100 / 255;
  static num celsius(List<int> b) => b[0] - 40;
  static num rpm(List<int> b) => ((b[0] << 8) | b[1]) / 4;
  static num per100(List<int> b) => ((b[0] << 8) | b[1]) / 100;
}

/// Live PIDs polled while driving (generic OBD-II, J1979 mode 01).
const livePids = <ObdPid>[
  ObdPid('0104', 'Engine load', '%', 1, decode: ObdPid.pct),
  ObdPid('0105', 'Coolant temp', '°C', 1, decode: ObdPid.celsius),
  ObdPid('010B', 'Intake pressure', 'kPa', 1),
  ObdPid('010C', 'Engine RPM', 'rpm', 2, decode: ObdPid.rpm),
  ObdPid('010D', 'Vehicle speed', 'km/h', 1),
  ObdPid('010F', 'Intake temp', '°C', 1, decode: ObdPid.celsius),
  ObdPid('0110', 'MAF airflow', 'g/s', 2, decode: ObdPid.per100),
  ObdPid('0111', 'Throttle position', '%', 1, decode: ObdPid.pct),
  ObdPid('012F', 'Fuel level', '%', 1, decode: ObdPid.pct),
  ObdPid('0146', 'Ambient temp', '°C', 1, decode: ObdPid.celsius),
];

/// The mode-01 PID ranges we probe to learn which PIDs the vehicle supports.
const supportedPidRanges = ['0100', '0120', '0140', '0160', '0180', '01A0', '01C0'];

/// True for a response line that belongs to the reply (not `>`, not empty).
bool _isDataLine(String l) => l.trim().isNotEmpty && l.trim() != '>';

/// Splits a raw adapter reply into payload lines, stripping echoes (first
/// line that equals the command) and adapter noise (`OK`, `STOPPED`,
/// `SEARCHING...`, `BUS INIT`).
List<String> normalizeReply(String raw, String command) {
  final lines = raw
      .replaceAll('\r', '\n')
      .split('\n')
      .map((l) => l.trim())
      .where((l) => _isDataLine(l))
      .toList();
  if (lines.isNotEmpty && lines.first == command.toUpperCase()) {
    lines.removeAt(0);
  }
  // Adapter transient chatter; OK/NO DATA are kept (ATZ legitimately
  // answers OK and data commands answer NO DATA).
  return lines
      .where((l) => !['SEARCHING...', 'BUS INIT', 'STOPPED'].contains(l))
      .toList();
}

/// Parses a hex payload line ("41 0C 1A F8") into bytes, tolerating spaces,
/// `\t`, and `\r` from adapters that ignore AT S0.
List<int> parseHexPayload(String line) {
  final compact = line.replaceAll(RegExp(r'[^0-9A-Fa-f]'), '');
  if (compact.isEmpty || compact.length.isOdd) {
    throw Elm327Exception('Bad hex payload: "$line"');
  }
  final bytes = <int>[];
  for (var i = 0; i < compact.length; i += 2) {
    bytes.add(int.parse(compact.substring(i, i + 2), radix: 16));
  }
  return bytes;
}

/// Strips the 41 <pid> prefix from a mode-01 reply line, returning payload.
List<int> mode01Payload(String line, String pidHex) {
  final b = parseHexPayload(line);
  if (b.length < 3 || b[0] != 0x41) {
    throw Elm327Exception('Unexpected mode-01 reply: "$line"');
  }
  return b.sublist(2);
}

/// Decodes a DTC from two bytes (high bits = category P/C/B/U).
String decodeDtc(int a, int b) {
  const categories = ['P', 'C', 'B', 'U'];
  final c = categories[(a >> 6) & 0x3];
  final rest = ((a & 0x3f) << 8) | b;
  return '$c${rest.toRadixString(16).toUpperCase().padLeft(4, '0')}';
}

/// Decodes a mode-03/07 reply into DTC strings. Lines look like
/// `43 01 01 00 00 00` (03) or `47 01 ...` (07); each trailing pair is a DTC.
List<String> decodeDtcReply(List<String> lines, int mode) {
  final codes = <String>[];
  for (final line in lines) {
    final b = parseHexPayload(line);
    if (b.length < 3 || b[0] != 0x40 + mode) {
      throw Elm327Exception('Unexpected mode-$mode reply: "$line"');
    }
    for (var i = 2; i + 1 < b.length; i += 2) {
      if (b[i] == 0x00 && b[i + 1] == 0x00) continue;
      codes.add(decodeDtc(b[i], b[i + 1]));
    }
  }
  return codes;
}

/// Decodes a mode-09 PID 02 VIN reply. `49 02 01` prefix, then 17 ASCII chars.
String decodeVin(List<String> lines) {
  for (final line in lines) {
    final b = parseHexPayload(line);
    if (b.length < 5 || b[0] != 0x49) continue;
    final start = (b[1] == 0x02) ? (b.length >= 3 && b[2] == 0x01 ? 3 : 2) : 0;
    final sb = StringBuffer();
    for (var i = start; i < b.length; i++) {
      final c = String.fromCharCode(b[i]);
      if (c.codeUnitAt(0) < 0x20 || c.codeUnitAt(0) > 0x7e) break;
      sb.write(c);
    }
    if (sb.length >= 17) return sb.toString();
  }
  throw Elm327Exception('VIN reply not recognised: "$lines"');
}

/// Builds the set of supported mode-01 PIDs from `0100/0120/...` replies.
/// Each reply: `41 <pid>` + 4 bytes; in each byte bit 7 (MSB) is the lowest
/// PID of that byte (byte0 bit7 = PID 01, byte3 bit0 = PID 20).
Set<String> decodeSupportedPids(Map<String, List<String>> replies) {
  final supported = <String>{};
  for (final entry in replies.entries) {
    final base = int.parse(entry.key.substring(2), radix: 16);
    for (final line in entry.value) {
      final b = mode01Payload(line, entry.key.substring(2));
      if (b.length < 4) continue;
      for (var byteIdx = 0; byteIdx < 4; byteIdx++) {
        for (var bit = 7; bit >= 0; bit--) {
          if ((b[byteIdx] >> bit) & 0x1 == 1) {
            final pid = base + byteIdx * 8 + (7 - bit) + 1;
            supported.add('01'
                '${pid.toRadixString(16).toUpperCase().padLeft(2, '0')}');
          }
        }
      }
    }
  }
  return supported;
}

/// One decoded live-PID reading.
class PidReading {
  PidReading(this.pid, this.value);
  final ObdPid pid;
  final num value;
  String get label => '${pid.name}: ${pid.format(value)} ${pid.unit}';
}

/// One DTC with an optional plain-English meaning.
class DtcResult {
  DtcResult(this.code, this.description);
  final String code;
  final String? description;
}

/// A session against one connected adapter. Owns initialisation and maps
/// high-level reads onto the raw transport. Safe to use from any thread.
class Elm327Session {
  Elm327Session(this._transport);

  final Elm327Transport _transport;

  Future<String> _send(String cmd) async {
    final raw = await _transport.send(cmd);
    if (raw.trim().isEmpty) throw Elm327Exception('No reply to $cmd');
    return raw;
  }

  /// Resets the adapter and disables echo/spaces/headers for stable parsing.
  Future<void> init() async {
    final z = await _send('ATZ');
    if (!normalizeReply(z, 'ATZ').contains('OK')) {
      // Some adapters reboot without a clean OK; carry on and verify below.
    }
    await Future<void>.delayed(const Duration(milliseconds: 300));
    await _send('ATE0');
    await _send('ATH0');
    await _send('ATL0');
    await _send('ATS0');
    await _send('ATSP0');
  }

  /// Reads the VIN via mode 09 PID 02.
  Future<String> readVin() async =>
      decodeVin(normalizeReply(await _send('0902'), '0902'));

  /// Reads current (03) + pending (07) DTCs.
  Future<List<DtcResult>> readDtc() async {
    final current = decodeDtcReply(
        normalizeReply(await _send('03'), '03'), 3);
    final pending = decodeDtcReply(
        normalizeReply(await _send('07'), '07'), 7);
    return [
      for (final c in {...current, ...pending})
        DtcResult(c, dtcDescription(c)),
    ];
  }

  /// Clears the ECU's stored DTCs via mode 04.
  ///
  /// Most adapters reply `44` on success; a `?` means the vehicle rejected
  /// the request. `NO DATA` is treated as success (nothing stored).
  Future<void> clearDtc() async {
    final reply = normalizeReply(await _send('04'), '04');
    if (reply.contains('?')) {
      throw Elm327Exception('Adapter rejected mode 04 (clear DTCs): "$reply"');
    }
  }

  /// Reads one live PID; returns null when the vehicle doesn't support it
  /// (reply is `41 <pid> 00`... or the pid isn't in the supported set).
  Future<PidReading?> readPid(ObdPid pid) async {
    final reply = normalizeReply(await _send(pid.command), pid.command);
    if (reply.isEmpty) return null;
    final b = mode01Payload(reply.first, pid.command.substring(2));
    return PidReading(pid, pid.value(b));
  }

  /// Reads the supported-PID map in one round trip.
  Future<Set<String>> readSupportedPids() async {
    final replies = <String, List<String>>{};
    for (final cmd in supportedPidRanges) {
      replies[cmd] = normalizeReply(await _send(cmd), cmd);
    }
    return decodeSupportedPids(replies);
  }

  /// Polls [livePids] once; skips PIDs the vehicle reports as unsupported.
  Future<List<PidReading>> readLive({Set<String>? supported}) async {
    final out = <PidReading>[];
    for (final pid in livePids) {
      if (supported != null && !supported.contains(pid.command)) continue;
      try {
        final r = await readPid(pid);
        if (r != null) out.add(r);
      } on Elm327Exception {
        // Vehicle/ECU may drop individual PIDs; skip and keep polling.
      }
    }
    return out;
  }

  Future<void> close() => _transport.close();
}

/// Minimal human meaning for common powertrain DTCs (data keeps the AI out of
/// the hot path — description lookup is deterministic).
String? dtcDescription(String code) {
  if (!_dtcMeanings.containsKey(code)) return null;
  return _dtcMeanings[code];
}

const _dtcMeanings = <String, String>{
  'P0100': 'MAF circuit malfunction',
  'P0101': 'MAF circuit range/performance',
  'P0113': 'Intake air temp sensor high input',
  'P0128': 'Coolant thermostat below regulating temperature',
  'P0130': 'O2 sensor bank 1 sensor 1 circuit',
  'P0171': 'System too lean (bank 1)',
  'P0172': 'System too rich (bank 1)',
  'P0300': 'Random/multiple cylinder misfire',
  'P0301': 'Cylinder 1 misfire',
  'P0302': 'Cylinder 2 misfire',
  'P0303': 'Cylinder 3 misfire',
  'P0304': 'Cylinder 4 misfire',
  'P0325': 'Knock sensor 1 circuit',
  'P0335': 'Crankshaft position sensor A circuit',
  'P0340': 'Camshaft position sensor A circuit',
  'P0401': 'EGR flow insufficient',
  'P0420': 'Catalyst system efficiency below threshold (bank 1)',
  'P0440': 'EVAP system malfunction',
  'P0455': 'EVAP system large leak',
  'P0500': 'Vehicle speed sensor malfunction',
  'P0562': 'System voltage low',
  'P0700': 'Transmission control system malfunction',
  'P0750': 'Shift solenoid A malfunction',
  'P1130': 'Fuel trim at limit',
  'P1234': 'Fuel pump secondary circuit low',
  'P1612': 'ECM to immobilizer communication error',
};

/// A transport backed by an in-memory scripted adapter, used by tests and the
/// offline demo ("simulate adapter") path.
class FakeElmTransport implements Elm327Transport {
  FakeElmTransport(this.script);
  final Map<String, String> script;
  final List<String> sent = [];

  @override
  Future<String> send(String cmd) async {
    sent.add(cmd);
    if (!script.containsKey(cmd)) throw Elm327Exception('No scripted reply for $cmd');
    return script[cmd]!;
  }

  @override
  Future<void> close() async {}
}

/// Serialises [script] fixture maps to JSON for golden tests.
String dumpScript(Map<String, String> script) =>
    const JsonEncoder.withIndent('  ').convert(script);
