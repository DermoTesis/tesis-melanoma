// Contratos de acceso a datos. Cada repositorio corresponde a un módulo del
// backend monolítico modular (Tabla 6): Identidad, Pacientes, Gestión de
// Casos (+ Inferencia), Validación Clínica, Informes y Auditoría.
//
// La primera versión usa implementaciones simuladas en memoria
// (lib/data/mock). Para conectar el backend real basta con implementar estas
// interfaces con clientes REST/Firebase y cambiarlas en
// lib/providers/repository_providers.dart.

import '../models/audit_event.dart';
import '../models/clinical_case.dart';
import '../models/patient.dart';
import '../models/prediction.dart';
import '../models/report.dart';
import '../models/user.dart';
import '../models/validation.dart';

/// Firebase Authentication + módulo Identidad.
abstract class AuthRepository {
  Stream<AppUser?> authStateChanges();
  AppUser? get currentUser;

  /// Lanza [AuthException] con un mensaje genérico ante cualquier fallo.
  Future<AppUser> signIn(String correo, String password);
  Future<void> signOut();

  /// Busca el enlace de activación enviado al correo (simulación del enlace).
  Future<ActivationTicket?> findActivation(String correo);
  Future<ActivationTicket?> getActivation(String uid);

  /// Define la contraseña e inicia sesión. Falla si el enlace venció.
  Future<AppUser> activateAccount(String uid, String password);

  /// Registra la aceptación fechada del alcance de apoyo diagnóstico.
  Future<AppUser> acceptScope();

  Future<PasswordResetTicket> requestPasswordReset(String correo);
  Future<void> resetPassword(String correo, String newPassword);

  /// Solo para la demo: vence el enlace de recuperación enviado.
  Future<PasswordResetTicket?> expireResetLink(String correo);
}

/// Módulo Identidad, funciones del administrador.
abstract class AdminRepository {
  Stream<List<AppUser>> watchUsers();

  /// Crea la cuenta pendiente de activación. El especialista la activa con el
  /// enlace que recibe por correo (en el backend real, el flujo de
  /// restablecimiento de contraseña de Firebase).
  Future<AppUser> createSpecialist({
    required String nombres,
    required String correo,
    required String dni,
    required String cmp,
    required bool colegiaturaVerificada,
  });
  Future<void> setClinicalAccess(String uid, bool enabled);
}

/// Módulo Pacientes.
abstract class PatientRepository {
  Stream<List<Patient>> watchPatients();
  Stream<Patient?> watchPatient(String id);
  Future<Patient?> findByHistoriaClinica(String hc);
  Future<Patient> registerPatient({
    required String numeroHistoriaClinica,
    required String nombres,
    required DateTime fechaNacimiento,
    required Sex sexo,
    required Phototype fototipo,
  });
  Future<Patient> registerConsent(String patientId);
  Future<Patient> revokeConsent(String patientId);
}

/// Módulo Gestión de Casos (incluye la invocación síncrona a Inferencia).
abstract class CaseRepository {
  Stream<List<ClinicalCase>> watchMyCases();
  Stream<ClinicalCase?> watchCase(String id);
  Stream<List<ClinicalCase>> watchCasesForPatient(String patientId);

  /// Registra el caso y lo envía a análisis. Sin conectividad queda en la
  /// cola local y se reenvía al recuperar la conexión (RF-02.4, RNF-08).
  Future<ClinicalCase> submitCase(CaseDraft draft, ClinicalData data);
  Future<void> retryAnalysis(String caseId);

  /// Orden manual del panel (RF-06.2). Lista vacía restablece el orden.
  Future<void> setManualOrder(List<String> caseIds);
  List<String> get manualOrder;

  Future<void> updateSuggestion(String caseId, String suggestion);
  Future<void> addInternalNote(String caseId, String text);
}

/// Módulo Validación Clínica.
abstract class ValidationRepository {
  Stream<List<ClinicalValidation>> watchValidations(String caseId);
  Future<ClinicalValidation> registerValidation({
    required String caseId,
    required ValidationDecision decision,
    required String sustentoClinico,
    String? examenesAdicionales,
    bool? sugerenciaTomada,
    LesionClass? claseFinal,
    String? complementaDe,
  });
}

/// Módulo Informes.
abstract class ReportRepository {
  Stream<CaseReport?> watchReport(String caseId);

  /// Cierra el caso; solo procede si existe una validación (RF-07.1).
  Future<CaseReport> closeCase(String caseId, String conductaClinica);

  /// Contenido exportable del informe, sin observaciones internas (RF-05.5).
  Future<ReportDocument> buildReportDocument(String caseId);
}

/// Módulo Auditoría.
abstract class AuditRepository {
  Stream<List<AuditEvent>> watchEvents();
}

/// Conectividad del dispositivo (en la demo se puede simular sin conexión).
abstract class ConnectivityService {
  bool get isOnline;
  Stream<bool> onlineChanges();
  void setOnline(bool online);
}
