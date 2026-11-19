import '../../core/errors/app_exception.dart';

/// Entrega el token que va en `Authorization: Bearer <token>` (I13).
abstract class TokenProvider {
  /// Token de la sesión actual, o null si no hay sesión.
  Future<String?> token();

  /// Inicia sesión y devuelve el uid. Lanza `AuthException` (genérica) si
  /// las credenciales no son válidas.
  Future<String> signIn(String correo, String password);

  Future<void> signOut();
}

/// Cuentas que siembra `backend/dermavia/local.py`.
abstract final class DevAccounts {
  static const adminEmail = 'admin@dermavia.local';
  static const specialistEmail = 'especialista@dermavia.local';
  static const newSpecialistEmail = 'nuevo@dermavia.local';

  static const uids = {
    adminEmail: 'admin-dev',
    specialistEmail: 'especialista-dev',
    newSpecialistEmail: 'especialista-nuevo',
  };

  /// Uid del administrador sembrado, para resolver el uid de las cuentas
  /// creadas durante la sesión del servidor local.
  static const adminUid = 'admin-dev';
}

/// Solo para el servidor local: el token `dev:<uid>` identifica al usuario sin
/// Firebase y el servidor no verifica la contraseña. Nunca se usa en la nube
/// (el backend se niega a arrancar en modo local dentro de Cloud Run).
class DevTokenProvider implements TokenProvider {
  DevTokenProvider({this.resolveUid});

  /// Busca el uid de un correo que no está en [DevAccounts] (p. ej. una cuenta
  /// dada de alta por el administrador durante la sesión del servidor).
  final Future<String?> Function(String correo)? resolveUid;

  String? _uid;

  String? get uid => _uid;

  @override
  Future<String?> token() async => _uid == null ? null : 'dev:$_uid';

  @override
  Future<String> signIn(String correo, String password) async {
    final email = correo.trim().toLowerCase();
    final uid = DevAccounts.uids[email] ?? await resolveUid?.call(email);
    if (uid == null || password.isEmpty) throw const AuthException();
    _uid = uid;
    return uid;
  }

  @override
  Future<void> signOut() async => _uid = null;
}
