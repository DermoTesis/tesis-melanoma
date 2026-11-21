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
    view: ImageView.foto1,
    source: CaptureSource.camara,
    localPath: '/tmp/p.jpg',
  );
  const secondPhoto = CaseImage(
    view: ImageView.foto2,
    source: CaptureSource.camara,
    localPath: '/tmp/a.jpg',
  );
  const data = ClinicalData(
      ubicacionLesion: 'Brazo derecho',
      tiempoAparicion: OnsetTime.entre3y12Meses,
      impresionClinica: ClinicalImpression.dudosa);

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
      const CaseDraft(patientId: 'p-jmamani', foto1: image, foto2: secondPhoto),
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
            CaseDraft(patientId: p.id, foto1: image, foto2: secondPhoto), data),
        throwsA(isA<ConsentRequiredException>()),
      );
      await patients.registerConsent(p.id);
      final c = await cases.submitCase(
          CaseDraft(patientId: p.id, foto1: image, foto2: secondPhoto), data);
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

    test('el caso exige la impresión clínica antes del análisis (D4)', () async {
      await loginSpecialist();
      const sinImpresion = ClinicalData(
          ubicacionLesion: 'Brazo derecho', tiempoAparicion: OnsetTime.entre3y12Meses);
      await expectLater(
        cases.submitCase(
            const CaseDraft(patientId: 'p-jmamani', foto1: image, foto2: secondPhoto),
            sinImpresion),
        throwsA(isA<AppException>()),
      );
    });

    test('el caso exige las dos imágenes', () async {
      await loginSpecialist();
      await expectLater(
        cases.submitCase(const CaseDraft(patientId: 'p-jmamani', foto1: image), data),
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
      final other = predicted == LesionClass.melanoma ? LesionClass.noMelanoma : LesionClass.melanoma;
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
      // D5: constancia del uso de la herramienta, con la versión.
      expect(doc.constanciaHerramienta,
          contains('Caso evaluado con apoyo de Dermavía (versión 20261004T172732Z_registro)'));
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
        const CaseDraft(patientId: 'p-jmamani', foto1: image, foto2: secondPhoto),
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

  group('Privacidad de los casos entre médicos', () {
    // Igual que el backend real: los casos son de quien los registró.
    Future<String> caseByRaul() async {
      await auth.signIn(DemoCredentials.adminEmail, DemoCredentials.adminPassword);
      await admin.setClinicalAccess(SeedData.raul, true);
      await auth.signOut();
      await auth.signIn(DemoCredentials.revokedEmail, DemoCredentials.specialistPassword);
      final c = await cases.submitCase(
          const CaseDraft(patientId: 'p-jmamani', foto1: image, foto2: secondPhoto), data);
      await settle();
      await auth.signOut();
      return c.id;
    }

    test('otro médico no ve el caso en la ficha del paciente ni en el detalle', () async {
      final id = await caseByRaul();
      await loginSpecialist();
      final ofPatient = await cases.watchCasesForPatient('p-jmamani').first;
      expect(ofPatient.map((c) => c.id), isNot(contains(id)));
      expect(ofPatient, isNotEmpty); // Los casos propios de Lucía sí aparecen.
      expect(await cases.watchCase(id).first, isNull);
      expect(await validations.watchValidations(id).first, isEmpty);
    });

    test('otro médico no puede validar, anotar ni cerrar el caso', () async {
      final id = await caseByRaul();
      await loginSpecialist();
      final notFound =
          throwsA(isA<AppException>().having((e) => e.message, 'message', 'Caso no encontrado.'));
      expect(b.cases[id]!.prediction, isNotNull); // Se rechaza por ser ajeno, no por el estado.
      await expectLater(
          validations.registerValidation(
              caseId: id,
              decision: ValidationDecision.confirmar,
              sustentoClinico: 'Patrón atípico.'),
          notFound);
      await expectLater(cases.addInternalNote(id, 'Nota'), notFound);
      await expectLater(cases.updateSuggestion(id, 'Biopsia'), notFound);
      await expectLater(reports.closeCase(id, 'Control'), notFound);
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

    test('con el mismo riesgo, el caso con alerta va primero (RF-06.2, A14)', () {
      final pending = b.cases.values.where((c) => c.isPendingValidation).toList()
        ..sort((a, b) => a.createdAt.compareTo(b.createdAt));
      final at = DateTime(2026, 11, 21);
      // Escalón del 7%: misma probabilidad calibrada, con y sin alerta. El
      // caso sin alerta es el más reciente, así que antes quedaba primero.
      final withAlert = pending.first.copyWith(
          prediction: MockInferenceEngine.fromModelOutput(0.015, at));
      final noAlert = pending.last.copyWith(
          prediction: MockInferenceEngine.fromModelOutput(0.010, at));
      expect(noAlert.createdAt.isAfter(withAlert.createdAt), isTrue);
      expect({withAlert.prediction!.percent, noAlert.prediction!.percent}, {7});

      final sorted = sortForPanel([noAlert, withAlert], const []);
      expect(sorted.first.prediction!.isAlert, isTrue);
      expect(sorted.last.prediction!.isAlert, isFalse);
    });
  });
}
