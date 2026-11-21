import 'package:firebase_auth/firebase_auth.dart';

import '../../core/errors/app_exception.dart';
import 'api_client.dart';
import 'password_link_throttle.dart';

/// Entrega el token que va en `Authorization: Bearer <token>` (I13):
/// [DevTokenProvider] con el servidor local y [FirebaseTokenProvider] en la nube.
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

/// Envía el correo de Firebase para definir la contraseña. Lo usan la
/// activación de una cuenta nueva y la recuperación (I15, I16): los dos flujos
/// usan la plantilla de "restablecer contraseña" y el enlace vence en 1 hora.
abstract class PasswordLinkSender {
  /// No avisa si el correo no existe (protección contra la enumeración de
  /// cuentas de Firebase), igual que el error genérico de HU04·CA2.
  Future<void> sendPasswordLink(String correo);
}

/// Lo que la app usa de Firebase Authentication. Existe para probar el mapeo
/// de errores sin Firebase (CONEXION_NUBE.md, N4 y N12). Los errores son
/// `FirebaseAuthException`.
abstract class FirebaseAuthGateway {
  /// Devuelve el uid.
  Future<String> signInWithEmailAndPassword(String email, String password);

  /// ID token del usuario actual (Firebase lo renueva solo antes de que venza),
  /// o null si no hay sesión.
  Future<String?> idToken();

  Future<void> signOut();

  Future<void> sendPasswordResetEmail(String email);
}

/// [FirebaseAuthGateway] con el plugin real. Solo se crea en modo `nube`,
/// después de `Firebase.initializeApp`.
class PluginFirebaseAuthGateway implements FirebaseAuthGateway {
  PluginFirebaseAuthGateway([FirebaseAuth? auth]) : _auth = auth ?? FirebaseAuth.instance;

  final FirebaseAuth _auth;

  @override
  Future<String> signInWithEmailAndPassword(String email, String password) async {
    final credential = await _auth.signInWithEmailAndPassword(email: email, password: password);
    final user = credential.user;
    if (user == null) throw FirebaseAuthException(code: 'user-not-found');
    return user.uid;
  }

  @override
  Future<String?> idToken() async => _auth.currentUser?.getIdToken();

  @override
  Future<void> signOut() => _auth.signOut();

  @override
  Future<void> sendPasswordResetEmail(String email) => _auth.sendPasswordResetEmail(email: email);
}

/// Firebase Authentication con correo y contraseña (I13, CONEXION_NUBE.md N4).
class FirebaseTokenProvider implements TokenProvider, PasswordLinkSender {
  FirebaseTokenProvider(this._auth, {PasswordLinkThrottle? throttle})
      : _throttle = throttle ?? PasswordLinkThrottle();

  final FirebaseAuthGateway _auth;

  /// Límite de envíos del correo para definir la contraseña: aplica a la
  /// recuperación, a "Tengo un enlace de activación" y al alta y reenvío del
  /// administrador, que pasan todos por [sendPasswordLink].
  final PasswordLinkThrottle _throttle;

  static const tooManyRequestsMessage =
      'Demasiados intentos. Espera unos minutos e inténtalo otra vez.';

  /// Códigos que no deben revelar qué dato falló (HU04·CA2). Una cuenta
  /// pendiente de activación todavía no tiene contraseña y cae aquí.
  static const _invalidCredentialCodes = {
    'invalid-credential',
    'wrong-password',
    'user-not-found',
    'invalid-email',
    'user-disabled',
  };

  @override
  Future<String> signIn(String correo, String password) async {
    final email = correo.trim();
    if (email.isEmpty || password.isEmpty) throw const AuthException();
    try {
      return await _auth.signInWithEmailAndPassword(email, password);
    } on FirebaseAuthException catch (e) {
      if (_invalidCredentialCodes.contains(e.code)) throw const AuthException();
      throw _commonError(e, 'No se pudo iniciar sesión. Inténtalo otra vez.');
    }
  }

  /// Si la renovación del token falla (p. ej. el administrador cambió el rol o
  /// quitó el acceso clínico y el backend revocó las sesiones), devuelve null:
  /// la petición sale sin token, el backend responde 401 y la app cierra la
  /// sesión (`onUnauthenticated`).
  @override
  Future<String?> token() async {
    try {
      return await _auth.idToken();
    } on FirebaseAuthException catch (e) {
      if (e.code == 'network-request-failed') throw const NetworkException();
      return null;
    }
  }

  @override
  Future<void> signOut() => _auth.signOut();

  /// Lanza `PasswordLinkCooldownException` si se pide otro enlace demasiado pronto.
  @override
  Future<void> sendPasswordLink(String correo) async {
    _throttle.check(correo);
    try {
      await _auth.sendPasswordResetEmail(correo.trim());
    } on FirebaseAuthException catch (e) {
      // Misma respuesta exista o no la cuenta (también para el límite).
      if (e.code != 'user-not-found' && e.code != 'invalid-email') {
        throw _commonError(e, 'No se pudo enviar el enlace. Inténtalo otra vez.');
      }
    }
    _throttle.record(correo);
  }

  static AppException _commonError(FirebaseAuthException e, String fallback) => switch (e.code) {
        'too-many-requests' => const AppException(tooManyRequestsMessage, code: 'too-many-requests'),
        'network-request-failed' => const NetworkException(),
        _ => AppException(fallback, code: 'auth/${e.code}'),
      };
}
