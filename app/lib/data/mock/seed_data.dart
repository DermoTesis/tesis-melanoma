import '../../domain/models/audit_event.dart';
import '../../domain/models/clinical_case.dart';
import '../../domain/models/patient.dart';
import '../../domain/models/prediction.dart';
import '../../domain/models/report.dart';
import '../../domain/models/user.dart';
import '../../domain/models/validation.dart';
import 'mock_backend.dart';
import 'mock_inference_engine.dart';

/// Credenciales de demostración (documentadas en el README).
abstract final class DemoCredentials {
  static const specialistEmail = 'lramirez@hospital.gob.pe';
  static const specialistPassword = 'Dermavia#2026';
  static const adminEmail = 'admin@hospital.gob.pe';
  static const adminPassword = 'Admin#2026!';
  static const pendingEmail = 'psalas@hospital.gob.pe';
  static const revokedEmail = 'rdiaz@hospital.gob.pe';
}

/// Datos de ejemplo tomados de los mockups.
abstract final class SeedData {
  static const establecimiento = 'Hospital II · Dermatología';
  static const lucia = 'u-lramirez';
  static const pedro = 'u-psalas';
  static const raul = 'u-rdiaz';
  static const admin = 'u-admin';

  static void apply(MockBackend b) {
    final now = b.now();
    DateTime ago({int days = 0, int hours = 0, int minutes = 0}) =>
        now.subtract(Duration(days: days, hours: hours, minutes: minutes));

    // --- Usuarios ---
    b.users[lucia] = AppUser(
      uid: lucia,
      role: UserRole.especialista,
      dni: '41827364',
      nombres: 'Dra. Lucía Ramírez',
      correo: DemoCredentials.specialistEmail,
      status: AccountStatus.activo,
      establecimiento: establecimiento,
      cmp: '045812',
      fechaVerificacion: ago(days: 300),
      verificadoPor: 'A. Paredes (admin)',
      termsAcceptedAt: ago(days: 299),
    );
    b.passwords[lucia] = DemoCredentials.specialistPassword;

    b.users[pedro] = AppUser(
      uid: pedro,
      role: UserRole.especialista,
      dni: '45120933',
      nombres: 'Dr. Pedro Salas Mendoza',
      correo: DemoCredentials.pendingEmail,
      status: AccountStatus.pendienteActivacion,
      establecimiento: establecimiento,
      cmp: '061274',
      fechaVerificacion: ago(minutes: 48),
      verificadoPor: 'A. Paredes (admin)',
    );
    b.activations[pedro] = ActivationTicket(
      uid: pedro,
      nombres: 'Dr. Pedro Salas Mendoza',
      correo: DemoCredentials.pendingEmail,
      expiresAt: now.add(const Duration(hours: 23, minutes: 12)),
    );

    b.users[raul] = AppUser(
      uid: raul,
      role: UserRole.especialista,
      dni: '40021876',
      nombres: 'Dr. Raúl Díaz',
      correo: DemoCredentials.revokedEmail,
      status: AccountStatus.activo,
      establecimiento: establecimiento,
      clinicalAccess: false,
      cmp: '038220',
      fechaVerificacion: ago(days: 400),
      verificadoPor: 'A. Paredes (admin)',
      termsAcceptedAt: ago(days: 399),
    );
    b.passwords[raul] = DemoCredentials.specialistPassword;

    b.users[admin] = AppUser(
      uid: admin,
      role: UserRole.admin,
      dni: '10293847',
      nombres: 'A. Paredes',
      correo: DemoCredentials.adminEmail,
      status: AccountStatus.activo,
      establecimiento: establecimiento,
    );
    b.passwords[admin] = DemoCredentials.adminPassword;

    // --- Pacientes ---
    Consent consent(DateTime at) => Consent(
          otorgado: true,
          fechaOtorgamiento: at,
          uidMedico: lucia,
          medicoNombre: 'Dra. Lucía Ramírez',
        );

    void patient(String id, String hc, String nombres, DateTime birth, Sex sex,
        Phototype ph, DateTime consentAt) {
      b.patients[id] = Patient(
        id: id,
        numeroHistoriaClinica: hc,
        nombres: nombres,
        fechaNacimiento: birth,
        sexo: sex,
        fototipo: ph,
        uidMedicoRegistro: lucia,
        consent: consent(consentAt),
      );
    }

    patient('p-mquispe', 'HC-004812', 'María Quispe Huamán',
        DateTime(now.year - 54, 2, 11), Sex.femenino, Phototype.iv, ago(days: 290));
    patient('p-jmamani', 'HC-003377', 'José Mamani Tito',
        DateTime(now.year - 61, 1, 5), Sex.masculino, Phototype.iv, ago(days: 40));
    patient('p-rflores', 'HC-005120', 'Rosa Flores Cárdenas',
        DateTime(now.year - 38, 1, 20), Sex.femenino, Phototype.iii, ago(days: 3));
    patient('p-lhuaman', 'HC-002904', 'Luis Huamán Paredes',
        DateTime(now.year - 47, 3, 2), Sex.masculino, Phototype.v, ago(days: 1));
    patient('p-crojas', 'HC-001190', 'Carlos Rojas Vargas',
        DateTime(now.year - 66, 6, 18), Sex.masculino, Phototype.iii, ago(days: 4));

    // --- Casos ---
    CaseImage img(ImageView v) => CaseImage(
          view: v,
          source: CaptureSource.camara,
          width: 3024,
          height: 4032,
        );

    void addCase(
      String id,
      String patientId,
      CaseStatus status,
      DateTime createdAt,
      String ubicacion,
      OnsetTime onset,
      Set<Symptom> symptoms, {
      // Salida sin calibrar del modelo; el riesgo que se muestra sale de la
      // calibración del artefacto (entre paréntesis en cada caso).
      double? modelOutput,
      // Impresión clínica registrada con el caso, antes de la predicción (D4).
      ClinicalImpression impression = ClinicalImpression.dudosa,
    }) {
      final prediction = modelOutput == null
          ? null
          : MockInferenceEngine.fromModelOutput(
              modelOutput, createdAt.add(const Duration(seconds: 20)));
      b.cases[id] = ClinicalCase(
        id: id,
        patientId: patientId,
        uidMedico: lucia,
        status: status,
        createdAt: createdAt,
        foto1: img(ImageView.foto1),
        foto2: img(ImageView.foto2),
        clinicalData: ClinicalData(
          ubicacionLesion: ubicacion,
          tiempoAparicion: onset,
          sintomas: symptoms,
          impresionClinica: impression,
        ),
        prediction: prediction,
        suggestion: prediction?.defaultSuggestion,
        analysisAttempts: 1,
      );
    }

    addCase('CASO-0192', 'p-mquispe', CaseStatus.pendienteValidacion,
        ago(hours: 52), 'Espalda, región escapular izquierda',
        OnsetTime.entre3y12Meses, {Symptom.cambioTamano, Symptom.cambioColor},
        modelOutput: 0.985, // 91%, posible melanoma
        impression: ClinicalImpression.sospechaMelanoma);
    addCase('CASO-0188', 'p-crojas', CaseStatus.pendienteValidacion,
        ago(hours: 49), 'Mejilla derecha', OnsetTime.masDe1Anio, {Symptom.picor},
        modelOutput: 0.215); // 20%, posible melanoma
    addCase('CASO-0196', 'p-jmamani', CaseStatus.pendienteValidacion,
        ago(hours: 9), 'Antebrazo derecho, cara dorsal', OnsetTime.entre3y12Meses,
        {Symptom.cambioTamano, Symptom.picor},
        modelOutput: 0.70); // 58%, posible melanoma
    addCase('CASO-0195', 'p-rflores', CaseStatus.pendienteValidacion,
        ago(hours: 5), 'Mejilla izquierda', OnsetTime.masDe1Anio, {},
        modelOutput: 0.0025, // 3%, sin alerta
        impression: ClinicalImpression.sinSospecha);
    addCase('CASO-0197', 'p-lhuaman', CaseStatus.errorAnalisis,
        ago(minutes: 40), 'Pierna izquierda, cara anterior', OnsetTime.menos3Meses,
        {Symptom.sangrado});

    // Historial cerrado de María Quispe.
    addCase('CASO-0141', 'p-mquispe', CaseStatus.cerrado, ago(days: 138),
        'Espalda, región lumbar', OnsetTime.masDe1Anio, {},
        modelOutput: 0.15); // 18%, posible melanoma
    addCase('CASO-0098', 'p-mquispe', CaseStatus.cerrado, ago(days: 290),
        'Brazo izquierdo', OnsetTime.masDe1Anio, {},
        modelOutput: 0.002, // 3%, sin alerta
        impression: ClinicalImpression.sinSospecha);

    void closed(String caseId, ValidationDecision decision, LesionClass clase,
        String sustento, String conducta, int daysAgo) {
      final c = b.cases[caseId]!;
      final at = ago(days: daysAgo, hours: -1);
      final v = ClinicalValidation(
        id: 'VAL-$caseId',
        caseId: caseId,
        uidEspecialista: lucia,
        especialistaNombre: 'Dra. Lucía Ramírez',
        cmp: '045812',
        decision: decision,
        claseFinal: clase,
        sustentoClinico: sustento,
        fechaValidacion: at,
        prediccionOriginal: c.prediction!,
      );
      b.validations[caseId] = [v];
      b.reports[caseId] = CaseReport(
        id: 'INF-$caseId',
        caseId: caseId,
        conductaClinica: conducta,
        fechaCierre: at.add(const Duration(minutes: 3)),
        validationId: v.id,
      );
    }

    closed(
      'CASO-0141',
      ValidationDecision.corregir,
      LesionClass.noMelanoma,
      'Patrón reticular regular, sin estructuras atípicas. Compatible con nevus displásico leve.',
      'Control dermatoscópico en 6 meses.',
      138,
    );
    closed(
      'CASO-0098',
      ValidationDecision.confirmar,
      LesionClass.noMelanoma,
      'Lesión simétrica, bordes regulares, color homogéneo.',
      'Control anual.',
      290,
    );

    b.caseSequence = 201;

    // --- Bitácora ---
    void event(AuditType t, String ref, String actor, DateTime at) {
      b.audit.add(AuditEvent(
          id: b.nextId('EV'), type: t, reference: ref, actorName: actor, timestamp: at));
    }

    event(AuditType.cambioRol, 'Acceso revocado · Dr. R. Díaz', 'A. Paredes',
        ago(hours: 2));
    event(AuditType.altaCuenta, 'Dr. Pedro Salas Mendoza', 'A. Paredes',
        ago(minutes: 48));
    event(AuditType.registroCaso, 'CASO-0197', 'Dra. Lucía Ramírez',
        ago(minutes: 40));
    event(AuditType.consentimiento, 'HC-002904', 'Dra. Lucía Ramírez',
        ago(days: 1));
    event(AuditType.anonimizacion, 'HC-000731', 'A. Paredes', ago(days: 2));
  }
}
