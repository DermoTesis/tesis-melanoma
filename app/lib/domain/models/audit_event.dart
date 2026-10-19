/// Eventos críticos que deben quedar en la bitácora auditable (RNF-17).
enum AuditType {
  altaCuenta,
  activacionCuenta,
  aceptacionAlcance,
  cambioRol,
  registroPaciente,
  consentimiento,
  revocacionConsentimiento,
  registroCaso,
  validacion,
  cierreCaso,
  anonimizacion,
}

extension AuditTypeLabel on AuditType {
  String get label {
    switch (this) {
      case AuditType.altaCuenta:
        return 'Alta de cuenta';
      case AuditType.activacionCuenta:
        return 'Activación de cuenta';
      case AuditType.aceptacionAlcance:
        return 'Aceptación del alcance';
      case AuditType.cambioRol:
        return 'Cambio de permisos';
      case AuditType.registroPaciente:
        return 'Registro de paciente';
      case AuditType.consentimiento:
        return 'Consentimiento';
      case AuditType.revocacionConsentimiento:
        return 'Revocación de consentimiento';
      case AuditType.registroCaso:
        return 'Registro de caso';
      case AuditType.validacion:
        return 'Validación registrada';
      case AuditType.cierreCaso:
        return 'Caso cerrado';
      case AuditType.anonimizacion:
        return 'Anonimización';
    }
  }
}

class AuditEvent {
  const AuditEvent({
    required this.id,
    required this.type,
    required this.reference,
    required this.actorName,
    required this.timestamp,
  });

  final String id;
  final AuditType type;

  /// Recurso afectado: CASO-0192, HC-006031, nombre del usuario, etc.
  final String reference;
  final String actorName;
  final DateTime timestamp;

  String get summary => '${type.label} · $reference';
}
