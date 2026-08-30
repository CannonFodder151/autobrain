import 'package:intl/intl.dart';

/// Parse a user-entered trip date/time. Accepts ISO strings plus the
/// Australian formats people actually type (`11/08/2026 3:30 pm`), instead of
/// [DateTime.tryParse] which only accepts strict ISO input.
DateTime? parseLogbookDateTime(String dateText, String timeText) {
  final date = dateText.trim();
  if (date.isEmpty) return null;
  final time = timeText.trim();

  final direct =
      DateTime.tryParse(time.isEmpty ? date : '$date $time');
  if (direct != null) return direct;

  final day = _parseDate(date);
  if (day == null) return null;
  if (time.isEmpty) return day;

  final t = _parseTime(time);
  if (t == null) return null;
  return DateTime(day.year, day.month, day.day, t.hour, t.minute);
}

DateTime? _parseDate(String s) {
  for (final fmt in const ['d/M/y', 'd-M-y', 'd.M.y', 'M/d/y', 'd MMM y', 'd MMMM y']) {
    try {
      final d = DateFormat(fmt).parseStrict(s);
      if (d.month < 1 || d.month > 12 || d.day < 1 || d.day > 31) return null;
      if (d.year < 1900 || d.year > 2200) return null;
      return d;
    } on FormatException {
      // try next format
    }
  }
  return null;
}

({int hour, int minute})? _parseTime(String s) {
  final m = RegExp(r'^(\d{1,2}):?(\d{2})?\s*(am|pm)?$', caseSensitive: false)
      .firstMatch(s);
  if (m == null) return null;
  var h = int.parse(m.group(1)!);
  final minute = int.tryParse(m.group(2) ?? '') ?? 0;
  if (minute > 59) return null;
  final ampm = m.group(3)?.toLowerCase();
  if (ampm == 'pm' && h <= 12) h = h == 12 ? 12 : h + 12;
  if (ampm == 'am' && h == 12) h = 0;
  if (h > 23) return null;
  return (hour: h, minute: minute);
}