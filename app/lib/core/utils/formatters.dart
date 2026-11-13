import 'package:intl/intl.dart';

abstract final class Fmt {
  static final _date = DateFormat('dd/MM/yyyy');
  static final _dayMonth = DateFormat('dd/MM');
  static final _time = DateFormat('HH:mm');
  static final _timeSec = DateFormat('HH:mm:ss');

  static String date(DateTime d) => _date.format(d);
  static String dayMonth(DateTime d) => _dayMonth.format(d);
  static String time(DateTime d) => _time.format(d);
  static String dateTime(DateTime d) => '${_date.format(d)} · ${_time.format(d)}';
  static String dateTimeSeconds(DateTime d) =>
      '${_date.format(d)} · ${_timeSec.format(d)}';

  /// "4 h", "35 min", "2 d"
  static String duration(Duration d) {
    if (d.inMinutes < 60) return '${d.inMinutes.clamp(0, 59)} min';
    if (d.inHours < 72) return '${d.inHours} h';
    return '${d.inDays} d';
  }

  static String percent(double p) => '${(p * 100).round()}%';

  /// Cuenta regresiva "23 h 12 min".
  static String countdown(Duration d) {
    if (d.isNegative) return 'vencido';
    final h = d.inHours;
    final m = d.inMinutes.remainder(60);
    return h > 0 ? '$h h ${m.toString().padLeft(2, '0')} min' : '$m min';
  }
}
