/// Usuario de la aplicación. Solo existen dos roles: el médico especialista
/// y el administrador del sistema (RF-01.1). El paciente nunca es usuario.
enum UserRole { especialista, admin }

/// Estado de la cuenta creada por el administrador.
enum AccountStatus { pendienteActivacion, activo }

class AppUser {
  const AppUser({
    required this.uid,
    required this.role,
    required this.dni,
    required this.nombres,
    required this.correo,
    required this.status,
    required this.establecimiento,
    this.clinicalAccess = true,
    this.cmp,
    this.fechaVerificacion,
    this.verificadoPor,
    this.termsAcceptedAt,
  });

  final String uid;
  final UserRole role;
  final String dni;
  final String nombres;
  final String correo;
  final AccountStatus status;
  final String establecimiento;

  /// Acceso a funciones clínicas; el administrador puede revocarlo (RF-01.4).
  final bool clinicalAccess;

  /// Número de colegiatura verificado ante el CMP (RF-01.3).
  final String? cmp;
  final DateTime? fechaVerificacion;
  final String? verificadoPor;

  /// Fecha de aceptación del alcance de apoyo diagnóstico (RF-05.3, RNF-06).
  final DateTime? termsAcceptedAt;

  bool get isAdmin => role == UserRole.admin;
  bool get isSpecialist => role == UserRole.especialista;
  bool get needsScopeAcceptance => isSpecialist && termsAcceptedAt == null;

  String get initials {
    final parts = nombres
        .replaceAll(RegExp(r'^(Dra?\.)\s*'), '')
        .split(' ')
        .where((p) => p.isNotEmpty)
        .toList();
    if (parts.isEmpty) return '?';
    if (parts.length == 1) return parts.first[0].toUpperCase();
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }

  AppUser copyWith({
    AccountStatus? status,
    bool? clinicalAccess,
    DateTime? termsAcceptedAt,
  }) {
    return AppUser(
      uid: uid,
      role: role,
      dni: dni,
      nombres: nombres,
      correo: correo,
      status: status ?? this.status,
      establecimiento: establecimiento,
      clinicalAccess: clinicalAccess ?? this.clinicalAccess,
      cmp: cmp,
      fechaVerificacion: fechaVerificacion,
      verificadoPor: verificadoPor,
      termsAcceptedAt: termsAcceptedAt ?? this.termsAcceptedAt,
    );
  }
}

/// Enlace de activación enviado al especialista dado de alta (HU01).
class ActivationTicket {
  const ActivationTicket({
    required this.uid,
    required this.nombres,
    required this.correo,
    required this.expiresAt,
  });

  final String uid;
  final String nombres;
  final String correo;
  final DateTime expiresAt;

  bool isExpired(DateTime now) => now.isAfter(expiresAt);
}

/// Enlace de recuperación de contraseña de tiempo limitado (HU03).
class PasswordResetTicket {
  const PasswordResetTicket({
    required this.correo,
    required this.expiresAt,
  });

  final String correo;
  final DateTime expiresAt;

  bool isExpired(DateTime now) => now.isAfter(expiresAt);
}
