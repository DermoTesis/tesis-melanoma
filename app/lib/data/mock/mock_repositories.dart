import '../../core/errors/app_exception.dart';
import '../../domain/models/audit_event.dart';
import '../../domain/models/clinical_case.dart';
import '../../domain/models/patient.dart';
import '../../domain/models/prediction.dart';
import '../../domain/models/report.dart';
import '../../domain/models/user.dart';
import '../../domain/models/validation.dart';
import '../../domain/repositories/repositories.dart';
import 'mock_backend.dart';

/// Política de contraseñas mostrada en la activación (pantalla 02).
abstract final class PasswordPolicy {
  static bool hasMinLength(String p) => p.length >= 10;
  static bool hasUpperAndNumber(String p) =>
      p.contains(RegExp(r'[A-ZÁÉÍÓÚÑ]')) && p.contains(RegExp(r'\d'));
  static bool hasSpecial(String p) => p.contains(RegExp(r'[^A-Za-z0-9ÁÉÍÓÚÑáéíóúñ]'));
  static bool isValid(String p) =>
      hasMinLength(p) && hasUpperAndNumber(p) && hasSpecial(p);
}

class MockAuthRepository implements AuthRepository {
  MockAuthRepository(this._b);
  final MockBackend _b;

  AppUser? _byEmail(String correo) {
    final email = correo.trim().toLowerCase();
    for (final u in _b.users.values) {
      if (u.correo.toLowerCase() == email) return u;
    }
    return null;
  }

  @override
  Stream<AppUser?> authStateChanges() =>
      _b.watch(() => _b.session == null ? null : _b.users[_b.session!.uid]);

  @override
  AppUser? get currentUser =>
      _b.session == null ? null : _b.users[_b.session!.uid];

  @override
  Future<AppUser> signIn(String correo, String password) async {
    await _b.delay();
    final user = _byEmail(correo);
    // Error genérico: no se indica qué dato falló (HU04·CA2).
    if (user == null ||
        user.status != AccountStatus.activo ||
        _b.passwords[user.uid] != password) {
      throw const AuthException();
    }
    if (user.isSpecialist && !user.clinicalAccess) {
      throw const PermissionDeniedException(
          'Tu acceso clínico fue revocado. Comunícate con el administrador del sistema.');
    }
    _b.session = user;
    _b.notify();
    return user;
  }

  @override
  Future<void> signOut() async {
    _b.session = null;
    _b.notify();
  }

  @override
  Future<ActivationTicket?> findActivation(String correo) async {
    await _b.delay();
    final user = _byEmail(correo);
    if (user == null) return null;
    return _b.activations[user.uid];
  }

  @override
  Future<ActivationTicket?> getActivation(String uid) async => _b.activations[uid];

  @override
  Future<AppUser> activateAccount(String uid, String password) async {
    await _b.delay();
    final ticket = _b.activations[uid];
    final user = _b.users[uid];
    if (ticket == null || user == null) {
      throw const AppException('El enlace de activación no es válido.');
    }
    if (ticket.isExpired(_b.now())) {
      throw const AppException(
          'El enlace de activación venció. Solicita uno nuevo al administrador.');
    }
    if (!PasswordPolicy.isValid(password)) {
      throw const AppException('La contraseña no cumple los requisitos mínimos.');
    }
    final activated = user.copyWith(status: AccountStatus.activo);
    _b.users[uid] = activated;
    _b.passwords[uid] = password;
    _b.activations.remove(uid);
    _b.session = activated;
    _b.log(AuditType.activacionCuenta, activated.nombres, actor: activated.nombres);
    _b.notify();
    return activated;
  }

  @override
  Future<AppUser> acceptScope() async {
    await _b.delay();
    final user = _b.requireSession();
    final updated = user.copyWith(termsAcceptedAt: _b.now());
    _b.users[user.uid] = updated;
    _b.session = updated;
    _b.log(AuditType.aceptacionAlcance, updated.nombres);
    _b.notify();
    return updated;
  }

  @override
  Future<PasswordResetTicket> requestPasswordReset(String correo) async {
    await _b.delay();
    final ticket = PasswordResetTicket(
      correo: correo.trim(),
      expiresAt: _b.now().add(const Duration(minutes: 30)),
    );
    // Solo se envía si el correo existe, pero la respuesta es siempre igual.
    if (_byEmail(correo) != null) _b.resets[correo.trim().toLowerCase()] = ticket;
    return ticket;
  }

  @override
  Future<PasswordResetTicket?> expireResetLink(String correo) async {
    final key = correo.trim().toLowerCase();
    final current = _b.resets[key];
    if (current == null) return null;
    final expired = PasswordResetTicket(
      correo: current.correo,
      expiresAt: _b.now().subtract(const Duration(minutes: 1)),
    );
    _b.resets[key] = expired;
    return expired;
  }

  @override
  Future<void> resetPassword(String correo, String newPassword) async {
    await _b.delay();
    final key = correo.trim().toLowerCase();
    final ticket = _b.resets[key];
    final user = _byEmail(correo);
    if (ticket == null || user == null) {
      throw const AppException('El enlace no es válido. Solicita uno nuevo.');
    }
    if (ticket.isExpired(_b.now())) {
      throw const AppException(
          'El enlace que abriste ya expiró y no puede usarse. Solicita uno nuevo.');
    }
    if (!PasswordPolicy.isValid(newPassword)) {
      throw const AppException('La contraseña no cumple los requisitos mínimos.');
    }
    _b.passwords[user.uid] = newPassword;
    _b.resets.remove(key);
  }
}

class MockAdminRepository implements AdminRepository {
  MockAdminRepository(this._b);
  final MockBackend _b;

  @override
  Stream<List<AppUser>> watchUsers() => _b.watch(() {
        final list = _b.users.values.where((u) => u.isSpecialist).toList()
          ..sort((a, b) => a.nombres.compareTo(b.nombres));
        return list;
      });

  @override
  Future<AppUser> createSpecialist({
    required String nombres,
    required String correo,
    required String dni,
    required String cmp,
    required bool colegiaturaVerificada,
  }) async {
    await _b.delay();
    final admin = _b.requireAdmin();
    if (!colegiaturaVerificada) {
      throw const AppException(
          'Debes verificar la habilitación ante el Colegio Médico del Perú.');
    }
    final email = correo.trim().toLowerCase();
    if (_b.users.values.any((u) => u.correo.toLowerCase() == email)) {
      throw const AppException('Ya existe una cuenta con ese correo.');
    }
    final uid = _b.nextId('u');
    final user = AppUser(
      uid: uid,
      role: UserRole.especialista,
      dni: dni.trim(),
      nombres: nombres.trim(),
      correo: email,
      status: AccountStatus.pendienteActivacion,
      establecimiento: admin.establecimiento,
      cmp: cmp.replaceAll(' ', ''),
      fechaVerificacion: _b.now(),
      verificadoPor: '${admin.nombres} (admin)',
    );
    _b.users[uid] = user;
    final ticket = ActivationTicket(
      uid: uid,
      nombres: user.nombres,
      correo: email,
      expiresAt: _b.now().add(const Duration(hours: 24)),
    );
    _b.activations[uid] = ticket;
    _b.log(AuditType.altaCuenta, user.nombres);
    _b.notify();
    return user;
  }

  @override
  Future<void> setClinicalAccess(String uid, bool enabled) async {
    await _b.delay();
    _b.requireAdmin();
    final user = _b.users[uid];
    if (user == null) throw const AppException('Usuario no encontrado.');
    _b.users[uid] = user.copyWith(clinicalAccess: enabled);
    _b.log(AuditType.cambioRol,
        '${enabled ? 'Acceso restablecido' : 'Acceso revocado'} · ${user.nombres}');
    _b.notify();
  }
}

class MockPatientRepository implements PatientRepository {
  MockPatientRepository(this._b);
  final MockBackend _b;

  @override
  Stream<List<Patient>> watchPatients() => _b.watch(() {
        final list = _b.patients.values.toList()
          ..sort((a, b) => a.nombres.compareTo(b.nombres));
        return list;
      });

  @override
  Stream<Patient?> watchPatient(String id) => _b.watch(() => _b.patients[id]);

  String _normalizeHc(String hc) => Patient.normalizeHc(hc);

  @override
  Future<Patient?> findByHistoriaClinica(String hc) async {
    await _b.delay();
    _b.requireClinician();
    final key = _normalizeHc(hc);
    for (final p in _b.patients.values) {
      if (p.numeroHistoriaClinica == key) return p;
    }
    return null;
  }

  @override
  Future<Patient> registerPatient({
    required String numeroHistoriaClinica,
    required String nombres,
    required DateTime fechaNacimiento,
    required Sex sexo,
    required Phototype fototipo,
  }) async {
    await _b.delay();
    final doctor = _b.requireClinician();
    final hc = _normalizeHc(numeroHistoriaClinica);
    if (hc.isEmpty || nombres.trim().isEmpty) {
      throw const AppException('Completa el número de historia clínica y los nombres.');
    }
    if (_b.patients.values.any((p) => p.numeroHistoriaClinica == hc)) {
      throw const AppException(
          'Ya existe un paciente con ese número de historia clínica.');
    }
    if (fechaNacimiento.isAfter(_b.now())) {
      throw const AppException('La fecha de nacimiento no puede ser futura.');
    }
    final patient = Patient(
      id: _b.nextId('p'),
      numeroHistoriaClinica: hc,
      nombres: nombres.trim(),
      fechaNacimiento: fechaNacimiento,
      sexo: sexo,
      fototipo: fototipo,
      uidMedicoRegistro: doctor.uid,
    );
    _b.patients[patient.id] = patient;
    _b.log(AuditType.registroPaciente, hc);
    _b.notify();
    return patient;
  }

  @override
  Future<Patient> registerConsent(String patientId) async {
    await _b.delay();
    final doctor = _b.requireClinician();
    final patient = _b.patients[patientId];
    if (patient == null) throw const AppException('Paciente no encontrado.');
    final updated = patient.copyWith(
      consent: Consent(
        otorgado: true,
        fechaOtorgamiento: _b.now(),
        uidMedico: doctor.uid,
        medicoNombre: doctor.nombres,
      ),
    );
    _b.patients[patientId] = updated;
    _b.log(AuditType.consentimiento, patient.numeroHistoriaClinica);
    _b.notify();
    return updated;
  }

  @override
  Future<Patient> revokeConsent(String patientId) async {
    await _b.delay();
    _b.requireClinician();
    final patient = _b.patients[patientId];
    final consent = patient?.consent;
    if (patient == null || consent == null || !consent.vigente) {
      throw const AppException('El paciente no tiene un consentimiento vigente.');
    }
    final updated = patient.copyWith(consent: consent.revoked(_b.now()));
    _b.patients[patientId] = updated;
    _b.log(AuditType.revocacionConsentimiento, patient.numeroHistoriaClinica);
    _b.notify();
    return updated;
  }
}

class MockCaseRepository implements CaseRepository {
  MockCaseRepository(this._b);
  final MockBackend _b;

  @override
  Stream<List<ClinicalCase>> watchMyCases() => _b.watch(() {
        final uid = _b.session?.uid;
        return _b.cases.values.where((c) => c.uidMedico == uid).toList();
      });

  @override
  Stream<ClinicalCase?> watchCase(String id) => _b.watch(() => _b.cases[id]);

  @override
  Stream<List<ClinicalCase>> watchCasesForPatient(String patientId) =>
      _b.watch(() {
        final list = _b.cases.values.where((c) => c.patientId == patientId).toList()
          ..sort((a, b) => b.createdAt.compareTo(a.createdAt));
        return list;
      });

  @override
  Future<ClinicalCase> submitCase(CaseDraft draft, ClinicalData data) async {
    await _b.delay();
    final doctor = _b.requireClinician();
    final patient = _b.patients[draft.patientId];
    if (patient == null) throw const AppException('Paciente no encontrado.');
    if (!patient.hasValidConsent) throw const ConsentRequiredException();
    if (!draft.hasBothImages) {
      throw const AppException(
          'El caso requiere dos fotos aptas de la lesión.');
    }
    if (data.ubicacionLesion.trim().isEmpty) {
      throw const AppException('Indica la ubicación corporal de la lesión.');
    }
    final id = _b.nextCaseId();
    final c = ClinicalCase(
      id: id,
      patientId: patient.id,
      uidMedico: doctor.uid,
      status: CaseStatus.registrado,
      createdAt: _b.now(),
      foto1: draft.foto1!,
      foto2: draft.foto2!,
      clinicalData: data,
      queuedOffline: !_b.online,
    );
    _b.cases[id] = c;
    _b.log(AuditType.registroCaso, id);
    _b.notify();
    if (_b.online) _b.startAnalysis(id);
    return _b.cases[id]!;
  }

  @override
  Future<void> retryAnalysis(String caseId) async {
    await _b.delay();
    _b.requireClinician();
    final c = _b.cases[caseId];
    if (c == null || c.status != CaseStatus.errorAnalisis) return;
    if (!_b.online) {
      throw const AppException('Sin conexión. Se reintentará al recuperarla.');
    }
    _b.startAnalysis(caseId);
  }

  @override
  List<String> get manualOrder => List.unmodifiable(_b.manualOrder);

  @override
  Future<void> setManualOrder(List<String> caseIds) async {
    _b.manualOrder = List.of(caseIds);
    _b.notify();
  }

  @override
  Future<void> updateSuggestion(String caseId, String suggestion) async {
    await _b.delay();
    _b.requireClinician();
    final c = _b.cases[caseId];
    if (c == null || c.status != CaseStatus.pendienteValidacion) {
      throw const AppException('La sugerencia solo puede editarse antes de validar.');
    }
    _b.cases[caseId] = suggestion.trim().isEmpty
        ? c.copyWith(clearSuggestion: true)
        : c.copyWith(suggestion: suggestion.trim());
    _b.notify();
  }

  @override
  Future<void> addInternalNote(String caseId, String text) async {
    await _b.delay();
    final doctor = _b.requireClinician();
    final c = _b.cases[caseId];
    if (c == null) throw const AppException('Caso no encontrado.');
    if (text.trim().isEmpty) throw const AppException('La observación está vacía.');
    _b.cases[caseId] = c.copyWith(internalNotes: [
      ...c.internalNotes,
      InternalNote(text: text.trim(), authorName: doctor.nombres, createdAt: _b.now()),
    ]);
    _b.notify();
  }
}

class MockValidationRepository implements ValidationRepository {
  MockValidationRepository(this._b);
  final MockBackend _b;

  @override
  Stream<List<ClinicalValidation>> watchValidations(String caseId) =>
      _b.watch(() => List.unmodifiable(_b.validations[caseId] ?? const []));

  @override
  Future<ClinicalValidation> registerValidation({
    required String caseId,
    required ValidationDecision decision,
    required String sustentoClinico,
    String? examenesAdicionales,
    bool? sugerenciaTomada,
    LesionClass? claseFinal,
    String? complementaDe,
  }) async {
    await _b.delay();
    final doctor = _b.requireClinician();
    final c = _b.cases[caseId];
    if (c == null) throw const AppException('Caso no encontrado.');
    final prediction = c.prediction;
    if (prediction == null) {
      throw const AppException(
          'La validación no está disponible hasta que termine la predicción preliminar.');
    }
    final existing = _b.validations[caseId] ?? const <ClinicalValidation>[];
    if (complementaDe == null) {
      if (c.status != CaseStatus.pendienteValidacion || existing.isNotEmpty) {
        throw const AppException(
            'El caso ya tiene una validación. Registra una validación complementaria.');
      }
    } else if (!existing.any((v) => v.id == complementaDe)) {
      throw const AppException('La validación a complementar no existe.');
    }
    if (sustentoClinico.trim().isEmpty) {
      throw const AppException(
          'El sustento clínico es obligatorio para guardar la validación.');
    }

    LesionClass? finalClass;
    switch (decision) {
      case ValidationDecision.confirmar:
        finalClass = prediction.clasePredicha;
      case ValidationDecision.corregir:
        if (claseFinal == null || claseFinal == prediction.clasePredicha) {
          throw const AppException(
              'Para corregir, selecciona una clasificación distinta a la predicción.');
        }
        finalClass = claseFinal;
      case ValidationDecision.descartar:
        finalClass = null;
    }

    final validation = ClinicalValidation(
      id: _b.nextId('VAL'),
      caseId: caseId,
      uidEspecialista: doctor.uid,
      especialistaNombre: doctor.nombres,
      cmp: doctor.cmp ?? '',
      decision: decision,
      claseFinal: finalClass,
      sustentoClinico: sustentoClinico.trim(),
      fechaValidacion: _b.now(),
      prediccionOriginal: prediction,
      examenesAdicionales: examenesAdicionales ?? c.suggestion,
      sugerenciaTomada: sugerenciaTomada,
      complementaDe: complementaDe,
    );
    // Solo inserción: nunca se modifica un registro existente.
    _b.validations[caseId] = [...existing, validation];
    if (c.status == CaseStatus.pendienteValidacion) {
      _b.cases[caseId] = c.copyWith(status: CaseStatus.validado);
    }
    _b.log(AuditType.validacion, caseId);
    _b.notify();
    return validation;
  }
}

class MockReportRepository implements ReportRepository {
  MockReportRepository(this._b);
  final MockBackend _b;

  @override
  Stream<CaseReport?> watchReport(String caseId) =>
      _b.watch(() => _b.reports[caseId]);

  @override
  Future<CaseReport> closeCase(String caseId, String conductaClinica) async {
    await _b.delay();
    _b.requireClinician();
    final c = _b.cases[caseId];
    final validations = _b.validations[caseId] ?? const [];
    if (c == null) throw const AppException('Caso no encontrado.');
    // Barrera de RF-07.1: sin validación no hay cierre ni informe.
    if (c.status != CaseStatus.validado || validations.isEmpty) {
      throw const ValidationRequiredException();
    }
    if (conductaClinica.trim().isEmpty) {
      throw const AppException('Registra la conducta o recomendación clínica.');
    }
    final report = CaseReport(
      id: _b.nextId('INF'),
      caseId: caseId,
      conductaClinica: conductaClinica.trim(),
      fechaCierre: _b.now(),
      validationId: validations.last.id,
    );
    _b.reports[caseId] = report;
    _b.cases[caseId] = c.copyWith(status: CaseStatus.cerrado);
    _b.log(AuditType.cierreCaso, caseId);
    _b.notify();
    return report;
  }

  @override
  Future<ReportDocument> buildReportDocument(String caseId) async {
    await _b.delay();
    _b.requireClinician();
    final c = _b.cases[caseId];
    final report = _b.reports[caseId];
    final validations = _b.validations[caseId] ?? const [];
    if (c == null || report == null || c.status != CaseStatus.cerrado ||
        validations.isEmpty) {
      throw const ValidationRequiredException();
    }
    final patient = _b.patients[c.patientId]!;
    final v = validations.last;
    return ReportDocument(
      caseId: c.id,
      fechaCierre: report.fechaCierre,
      pacienteNombre: patient.nombres,
      historiaClinica: patient.numeroHistoriaClinica,
      ubicacionLesion: c.clinicalData.ubicacionLesion,
      conclusion: v.reportConclusion,
      conducta: report.conductaClinica,
      especialistaNombre: v.especialistaNombre,
      cmp: v.cmp,
      establecimiento: _b.users[v.uidEspecialista]?.establecimiento ?? '',
      alcance: kScopeNotice,
      foto1Path: c.foto1.localPath,
      foto2Path: c.foto2.localPath,
    );
  }
}

class MockAuditRepository implements AuditRepository {
  MockAuditRepository(this._b);
  final MockBackend _b;

  @override
  Stream<List<AuditEvent>> watchEvents() => _b.watch(() {
        final list = List.of(_b.audit)
          ..sort((a, b) => b.timestamp.compareTo(a.timestamp));
        return list;
      });
}

class MockConnectivityService implements ConnectivityService {
  MockConnectivityService(this._b);
  final MockBackend _b;

  @override
  bool get isOnline => _b.online;

  @override
  Stream<bool> onlineChanges() => _b.watch(() => _b.online);

  @override
  void setOnline(bool online) => _b.setOnline(online);
}
