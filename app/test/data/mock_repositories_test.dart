import 'package:dermavia/core/errors/app_exception.dart';
import 'package:dermavia/data/mock/mock_backend.dart';
import 'package:dermavia/data/mock/mock_inference_engine.dart';
import 'package:dermavia/data/mock/mock_repositories.dart';
import 'package:dermavia/data/mock/seed_data.dart';
import 'package:dermavia/domain/models/clinical_case.dart';
import 'package:dermavia/domain/models/patient.dart';
import 'package:dermavia/domain/models/prediction.dart';
import 'package:dermavia/domain/models/validation.dart';
import 'package:dermavia/providers/case_providers.dart';
import 'package:flutter_test/flutter_test.dart';

Future<void> settle() => Future<void>.delayed(const Duration(milliseconds: 5));

void main() {
  late MockBackend b;
  late MockAuthRepository auth;
  late MockPatientRepository patients;
  late MockCaseRepository cases;
  late MockValidationRepository validations;
  late MockReportRepository reports;
  late MockAdminRepository admin;

  const image = CaseImage(
    view: ImageView.panoramica,
    source: CaptureSource.camara,
    conDermatoscopio: true,
    localPath: '/tmp/p.jpg',
  );
  const closeUp = CaseImage(
    view: ImageView.acercamiento,
    source: CaptureSource.camara,
    conDermatoscopio: true,
    localPath: '/tmp/a.jpg',
  );
  const data = ClinicalData(
      ubicacionLesion: 'Brazo derecho', tiempoAparicion: OnsetTime.entre3y12Meses);

  setUp(() {
    b = MockBackend(
      latency: Duration.zero,
      analysisDuration: Duration.zero,
      schedulerInterval: null,
    );
    auth = MockAuthRepository(b);
    patients = MockPatientRepository(b);
    cases = MockCaseRepository(b);
    validations = MockValidationRepository(b);
    reports = MockReportRepository(b);
    admin = MockAdminRepository(b);
  });

  tearDown(() => b.dispose());

  Future<void> loginSpecialist() => auth.signIn(
      DemoCredentials.specialistEmail, DemoCredentials.specialistPassword);

  Future<ClinicalCase> pendingCase() async {
    await loginSpecialist();
    final c = await cases.submitCase(
      const CaseDraft(patientId: 'p-jmamani', panoramica: image, acercamiento: closeUp),
      data,
    );
    await settle();
    return b.cases[c.id]!;
  }

  group('Autenticación', () {
    test('el error de credenciales es genérico (HU04·CA2)', () async {
      final wrongPassword = auth.signIn(DemoCredentials.specialistEmail, 'mala');
      await expectLater(wrongPassword, throwsA(isA<AuthException>()));
      final unknownUser = auth.signIn('nadie@hospital.gob.pe', 'x');
      await expectLater(unknownUser, throwsA(isA<AuthException>()));
      expect(const AuthException().message, contains('Correo o contraseña incorrectos'));
    });

    test('una cuenta con acceso revocado no ingresa', () async {
      await expectLater(
        auth.signIn(DemoCredentials.revokedEmail, DemoCredentials.specialistPassword),
        throwsA(isA<PermissionDeniedException>()),
      );
    });

    test('la activación exige contraseña válida y luego el alcance', () async {
      await expectLater(auth.activateAccount(SeedData.pedro, 'corta'), throwsA(isA<AppException>()));
      final user = await auth.activateAccount(SeedData.pedro, 'ClaveSegura#2026');
      expect(user.needsScopeAcceptance, isTrue);
      final accepted = await auth.acceptScope();
      expect(accepted.termsAcceptedAt, isNotNull);
    });

    test('solo el administrador da de alta especialistas (RF-01.3)', () async {
      await loginSpecialist();
      await expectLater(
        admin.createSpecialist(
            nombres: 'X', correo: 'x@h.pe', dni: '12345678', cmp: '1', colegiaturaVerificada: true),
        throwsA(isA<PermissionDeniedException>()),
      );
    });
  });

  group('Registro y consentimiento', () {
    test('no se crea un caso sin consentimiento vigente (RF-02.6)', () async {
      await loginSpecialist();
      final p = await patients.registerPatient(
        numeroHistoriaClinica: 'hc-009999',
        nombres: 'Ana Torres Ccori',
        fechaNacimiento: DateTime(1968, 3, 12),
        sexo: Sex.femenino,
        fototipo: Phototype.iii,
      );
      expect(p.numeroHistoriaClinica, 'HC-009999');
      await expectLater(
        cases.submitCase(
            CaseDraft(patientId: p.id, panoramica: image, acercamiento: closeUp), data),
        throwsA(isA<ConsentRequiredException>()),
      );
      await patients.registerConsent(p.id);
      final c = await cases.submitCase(
          CaseDraft(patientId: p.id, panoramica: image, acercamiento: closeUp), data);
      expect(c.status, CaseStatus.enAnalisis);
    });

    test('no se duplica un número de historia clínica', () async {
      await loginSpecialist();
      await expectLater(
        patients.registerPatient(
          numeroHistoriaClinica: 'HC-004812',
          nombres: 'Duplicado',
          fechaNacimiento: DateTime(1980),
          sexo: Sex.femenino,
          fototipo: Phototype.iv,
        ),
        throwsA(isA<AppException>()),
      );
    });

    test('el caso exige las dos imágenes', () async {
      await loginSpecialist();
      await expectLater(
        cases.submitCase(const CaseDraft(patientId: 'p-jmamani', panoramica: image), data),
        throwsA(isA<AppException>()),
      );
    });
  });

  group('Flujo obligatorio de validación (RF-07.1)', () {
    test('el envío produce una predicción preliminar pendiente', () async {
      final c = await pendingCase();
      expect(c.status, CaseStatus.pendienteValidacion);
      expect(c.prediction, isNotNull);
      expect(c.prediction!.umbralOperativo, ModelArtifact.calibratedThreshold);
    });

    test('la validación exige sustento clínico (RF-04.3)', () async {
      final c = await pendingCase();
      await expectLater(
        validations.registerValidation(
            caseId: c.id, decision: ValidationDecision.confirmar, sustentoClinico: '   '),
        throwsA(isA<AppException>()),
      );
      expect(b.cases[c.id]!.status, CaseStatus.pendienteValidacion);
    });

    test('no se cierra ni se genera informe sin validación', () async {
      final c = await pendingCase();
      await expectLater(reports.closeCase(c.id, 'Control'), throwsA(isA<ValidationRequiredException>()));
      await expectLater(reports.buildReportDocument(c.id), throwsA(isA<ValidationRequiredException>()));
    });

    test('corregir conserva la predicción original y el registro es inmutable', () async {
      final c = await pendingCase();
      final predicted = c.prediction!.clasePredicha;
      final other = predicted == LesionClass.maligno ? LesionClass.benigno : LesionClass.maligno;
      final v = await validations.registerValidation(
        caseId: c.id,
        decision: ValidationDecision.corregir,
        claseFinal: other,
        sustentoClinico: 'Patrón reticular regular.',
      );
      expect(v.claseFinal, other);
      expect(v.prediccionOriginal.clasePredicha, predicted);
      expect(b.cases[c.id]!.prediction!.clasePredicha, predicted);

      // Una segunda validación "normal" no puede sobrescribir la primera.
      await expectLater(
        validations.registerValidation(
            caseId: c.id, decision: ValidationDecision.confirmar, sustentoClinico: 'Otra'),
        throwsA(isA<AppException>()),
      );
      // Sí se admite una validación complementaria, que se añade.
      await validations.registerValidation(
        caseId: c.id,
        decision: ValidationDecision.confirmar,
        sustentoClinico: 'Revisión posterior',
        complementaDe: v.id,
      );
      expect(b.validations[c.id]!.length, 2);
      expect(b.validations[c.id]!.first.sustentoClinico, 'Patrón reticular regular.');
    });

    test('el informe excluye las observaciones internas (RF-05.5)', () async {
      final c = await pendingCase();
      await validations.registerValidation(
          caseId: c.id, decision: ValidationDecision.confirmar, sustentoClinico: 'Asimetría.');
      await cases.addInternalNote(c.id, 'NOTA-SECRETA antecedente familiar');
      await reports.closeCase(c.id, 'Biopsia excisional');
      expect(b.cases[c.id]!.status, CaseStatus.cerrado);

      final doc = await reports.buildReportDocument(c.id);
      expect(doc.conducta, 'Biopsia excisional');
      expect(doc.alcance, contains('No reemplaza el criterio médico'));
      final everything = [
        doc.conclusion,
        doc.conducta,
        doc.pacienteNombre,
        doc.ubicacionLesion,
        doc.alcance,
      ].join(' ');
      expect(everything, isNot(contains('NOTA-SECRETA')));
    });
  });

  group('Conectividad y tareas periódicas', () {
    test('sin conexión el caso queda en cola y se envía al reconectar (RNF-08)', () async {
      await loginSpecialist();
      b.setOnline(false);
      final c = await cases.submitCase(
        const CaseDraft(patientId: 'p-jmamani', panoramica: image, acercamiento: closeUp),
        data,
      );
      expect(c.status, CaseStatus.registrado);
      expect(c.queuedOffline, isTrue);
      b.setOnline(true);
      await settle();
      expect(b.cases[c.id]!.status, CaseStatus.pendienteValidacion);
      expect(b.cases[c.id]!.queuedOffline, isFalse);
    });

    test('Cloud Scheduler reprocesa los casos con error de análisis', () async {
      expect(b.cases['CASO-0197']!.status, CaseStatus.errorAnalisis);
      b.runScheduledTasks();
      await settle();
      // El primer intento simulado falla; el siguiente tiene éxito.
      if (b.cases['CASO-0197']!.status == CaseStatus.errorAnalisis) {
        b.runScheduledTasks();
        await settle();
      }
      expect(b.cases['CASO-0197']!.status, CaseStatus.pendienteValidacion);
    });
  });

  group('Panel', () {
    test('ordena por probabilidad y respeta el orden manual (RF-06.2)', () {
      final pending = b.cases.values.where((c) => c.isPendingValidation).toList();
      final sorted = sortForPanel(pending, const []);
      final probs = sorted.map((c) => c.prediction!.probabilidadMalignidad).toList();
      expect(probs, orderedEquals([...probs]..sort((a, b) => b.compareTo(a))));

      final manual = sortForPanel(pending, ['CASO-0195']);
      expect(manual.first.id, 'CASO-0195');
    });
  });
}
