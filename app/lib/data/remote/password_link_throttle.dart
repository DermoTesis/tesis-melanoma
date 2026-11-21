import '../../core/errors/app_exception.dart';

/// Se pidió un enlace para definir la contraseña demasiado pronto.
class PasswordLinkCooldownException extends AppException {
  const PasswordLinkCooldownException(super.message, this.remaining)
      : super(code: 'link-cooldown');

  /// Cuánto falta para poder pedir otro enlace.
  final Duration remaining;
}

/// Límite de envíos del correo para definir la contraseña, en el dispositivo.
///
/// Firebase también limita los envíos en el servidor (`too-many-requests`), pero su
/// límite es amplio: sin esto, la app permite llenar de correos la bandeja de alguien
/// tocando "Reenviar enlace". Cuenta los envíos por correo pedido, exista o no la cuenta,
/// así que no revela si está registrada (HU04·CA2). Vive en memoria: reiniciar la app lo
/// borra, y entonces queda el límite de Firebase.
class PasswordLinkThrottle {
  PasswordLinkThrottle({DateTime Function()? clock}) : _now = clock ?? DateTime.now;

  /// Tiempo mínimo entre dos enlaces al mismo correo.
  static const cooldown = Duration(seconds: 60);

  /// Máximo de enlaces desde el dispositivo, a cualquier correo, en [window].
  static const maxPerWindow = 5;
  static const window = Duration(minutes: 15);

  final DateTime Function() _now;
  final _lastByEmail = <String, DateTime>{};
  final _recent = <DateTime>[];

  static String _key(String correo) => correo.trim().toLowerCase();

  /// Lanza [PasswordLinkCooldownException] si todavía no se puede enviar a [correo].
  void check(String correo) {
    final now = _now();
    final last = _lastByEmail[_key(correo)];
    if (last != null) {
      final remaining = cooldown - now.difference(last);
      if (remaining > Duration.zero) {
        final seconds = (remaining.inMilliseconds / 1000).ceil();
        throw PasswordLinkCooldownException(
            'Ya se envió un enlace a este correo hace poco. Podrás pedir otro en $seconds s.',
            remaining);
      }
    }
    _recent.removeWhere((t) => now.difference(t) >= window);
    if (_recent.length >= maxPerWindow) {
      throw PasswordLinkCooldownException(
          'Se enviaron demasiados enlaces desde este dispositivo. Espera unos minutos e '
          'inténtalo otra vez.',
          window - now.difference(_recent.first));
    }
  }

  /// Registra un envío hecho. Solo los exitosos: si falló (sin red), se puede reintentar.
  void record(String correo) {
    final now = _now();
    _lastByEmail[_key(correo)] = now;
    _recent.add(now);
  }
}
