/// Error de negocio con un mensaje apto para mostrar al médico (RNF-16).
class AppException implements Exception {
  const AppException(this.message, {this.code = 'error'});

  final String message;
  final String code;

  @override
  String toString() => message;
}

class AuthException extends AppException {
  const AuthException()
      : super(
          'Correo o contraseña incorrectos. Verifica tus datos e inténtalo otra vez.',
          code: 'auth/invalid-credentials',
        );
}

class PermissionDeniedException extends AppException {
  const PermissionDeniedException([
    super.message = 'No tienes permisos para realizar esta acción.',
  ]) : super(code: 'permission-denied');
}

class ConsentRequiredException extends AppException {
  const ConsentRequiredException()
      : super(
          'El paciente no tiene un consentimiento informado vigente. '
          'Regístralo antes de capturar imágenes.',
          code: 'consent-required',
        );
}

class ValidationRequiredException extends AppException {
  const ValidationRequiredException()
      : super(
          'El caso no puede cerrarse ni generar su informe sin una validación médica registrada.',
          code: 'validation-required',
        );
}
