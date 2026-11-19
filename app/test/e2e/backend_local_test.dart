// Prueba de extremo a extremo contra el servidor local del backend
// (INTEGRACION_BACKEND.md, I25). Se salta salvo que se defina la URL. En
// PowerShell (ver README.md, "Backend real (servidor local)"):
//
//   # Terminal 1, en backend\ (sin DERMAVIA_URL_BASE: las fotos van a 127.0.0.1)
//   .venv\Scripts\python.exe -m dermavia.local --puerto 8080
//   # Terminal 2, en la carpeta app
//   $env:DERMAVIA_E2E_URL = "http://127.0.0.1:8080"; flutter test test/e2e
//
// En bash: `DERMAVIA_E2E_URL=http://127.0.0.1:8080 flutter test test/e2e`.
//
// Recorre el flujo obligatorio con los repositorios REST reales: paciente →
// consentimiento → caso con dos fotos → predicción → validación → cierre →
// informe. Si el servidor no tiene el modelo, el caso queda en ERROR_ANALISIS y
// la prueba lo informa en vez de seguir.

import 'dart:async';
import 'dart:io';

import 'package:dermavia/data/remote/api_client.dart';
import 'package:dermavia/data/remote/local_case_store.dart';
import 'package:dermavia/data/remote/refresh_hub.dart';
import 'package:dermavia/data/remote/rest_repositories.dart';
import 'package:dermavia/data/remote/token_provider.dart';
import 'package:dermavia/domain/models/clinical_case.dart';
import 'package:dermavia/domain/models/patient.dart';
import 'package:dermavia/domain/models/validation.dart';
import 'package:dermavia/domain/repositories/repositories.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;

class _Online implements ConnectivityService {
  @override
  bool get isOnline => true;
  @override
  Stream<bool> onlineChanges() => const Stream.empty();
  @override
  void setOnline(bool online) {}
}

void main() {
  final url = Platform.environment['DERMAVIA_E2E_URL'];

  test('flujo completo del caso contra el servidor local', () async {
    final tokens = DevTokenProvider();
    final api = ApiClient(baseUrl: url!, token: tokens.token);
    final hub = RefreshHub(pollInterval: null);
    final store = LocalCaseStore.memory();
    final auth = RestAuthRepository(api, tokens);
    final patients = RestPatientRepository(api, hub);
    final cases = RestCaseRepository(api, hub, store, _Online());
    final validations = RestValidationRepository(api, hub);
    final reports = RestReportRepository(api, hub, store);
    final dir = await Directory.systemTemp.createTemp('dermavia_e2e');
    addTearDown(() async {
      cases.dispose();
      hub.dispose();
      api.close();
      await dir.delete(recursive: true);
    });

    final user = await auth.signIn(DevAccounts.specialistEmail, 'dev');
    expect(user.isSpecialist, isTrue);

    final hc = 'E2E-${DateTime.now().millisecondsSinceEpoch}';
    final patient = await patients.registerPatient(
      numeroHistoriaClinica: hc,
      nombres: 'Paciente de prueba',
      fechaNacimiento: DateTime(1980, 1, 15),
      sexo: Sex.femenino,
      fototipo: Phototype.iii,
    );
    expect((await patients.findByHistoriaClinica(hc))?.id, patient.id);
    await patients.registerConsent(patient.id);

    // Dos fotos 4:3 como las del entrenamiento (600×450).
    CaseImage photo(ImageView view, int shade) {
      final image = img.Image(width: 600, height: 450);
      img.fill(image, color: img.ColorRgb8(shade, shade ~/ 2, shade ~/ 3));
      final file = File('${dir.path}/${view.name}.jpg')..writeAsBytesSync(img.encodeJpg(image));
      return CaseImage(view: view, localPath: file.path);
    }

    final created = await cases.submitCase(
      CaseDraft(
        patientId: patient.id,
        foto1: photo(ImageView.foto1, 180),
        foto2: photo(ImageView.foto2, 120),
      ),
      const ClinicalData(ubicacionLesion: 'Antebrazo izquierdo', tiempoAparicion: OnsetTime.noSabe),
    );
    expect(created.queuedOffline, isFalse);

    // El análisis corre en segundo plano: se consulta el estado.
    ClinicalCase? c;
    for (var i = 0; i < 120; i++) {
      c = await cases.watchCase(created.id).first;
      if (c!.status == CaseStatus.pendienteValidacion || c.status == CaseStatus.errorAnalisis) break;
      await Future<void>.delayed(const Duration(seconds: 1));
    }
    if (c!.status == CaseStatus.errorAnalisis) {
      markTestSkipped('El servidor no pudo analizar el caso: ${c.lastError}');
      return;
    }
    expect(c.status, CaseStatus.pendienteValidacion);
    expect(c.prediction, isNotNull);
    expect(c.foto1.remoteUrl, isNotNull);

    await expectLater(reports.closeCase(c.id, 'Control'), throwsA(anything));

    await validations.registerValidation(
      caseId: c.id,
      decision: ValidationDecision.confirmar,
      sustentoClinico: 'Prueba de extremo a extremo.',
    );
    await reports.closeCase(c.id, 'Control dermatoscópico en 6 meses.');
    final doc = await reports.buildReportDocument(c.id);
    expect(doc.historiaClinica, Patient.normalizeHc(hc));
    expect(doc.alcance, isNotEmpty);
  }, skip: url == null ? 'Define DERMAVIA_E2E_URL para probar contra el servidor local' : false,
      timeout: const Timeout(Duration(minutes: 3)));
}
