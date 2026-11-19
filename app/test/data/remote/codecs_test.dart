import 'package:dermavia/core/utils/formatters.dart';
import 'package:dermavia/data/remote/codecs.dart';
import 'package:dermavia/domain/models/audit_event.dart';
import 'package:dermavia/domain/models/clinical_case.dart';
import 'package:dermavia/domain/models/patient.dart';
import 'package:dermavia/domain/models/prediction.dart';
import 'package:dermavia/domain/models/user.dart';
import 'package:dermavia/domain/models/validation.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fixtures.dart';

void main() {
  group('Contrato del backend (INTEGRACION_BACKEND.md)', () {
    test('el usuario se lee de UsuarioOut', () {
      final u = userFromJson(userJson());
      expect(u.role, UserRole.especialista);
      expect(u.status, AccountStatus.activo);
      expect(u.cmp, '12345');
      expect(u.needsScopeAcceptance, isFalse);
      expect(userFromJson(userJson(aceptacion: null)).needsScopeAcceptance, isTrue);
    });

    test('el paciente trae su consentimiento y la fecha de nacimiento sin hora', () {
      final p = patientFromJson(patientJson());
      expect(p.fototipo, Phototype.iv);
      expect(p.sexo, Sex.femenino);
      expect(p.fechaNacimiento, DateTime(1970, 5, 2));
      expect(p.hasValidConsent, isTrue);
      expect(p.consent!.uidMedico, isNull);
      expect(patientFromJson(patientJson(consent: false)).hasValidConsent, isFalse);
    });

    test('la historia clínica se normaliza igual que el backend', () {
      expect(Patient.normalizeHc(' hc - 001 '), 'HC-001');
    });

    test('la predicción trae la clase decidida y la banda (I1, I2, RF-03.3)', () {
      // En el escalón del 7%, la clase no se puede deducir de la probabilidad:
      // la app usa la que manda el backend.
      final alerta = predictionFromJson(predictionJson());
      final sinAlerta = predictionFromJson(
          predictionJson(clase: 'no_melanoma', banda: 'sin_alerta'));
      expect(alerta.probabilidadMalignidad, sinAlerta.probabilidadMalignidad);
      expect(alerta.clasePredicha, LesionClass.melanoma);
      expect(alerta.isAlert, isTrue);
      expect(sinAlerta.clasePredicha, LesionClass.noMelanoma);
      expect(sinAlerta.confidence, PredictionConfidence.benigna);
      expect(alerta.confidence, PredictionConfidence.baja);
      expect(alerta.alertPercent, 7);
      expect(alerta.versionModelo, '20261004T172732Z_registro');
    });

    test('la banda del backend manda sobre los cortes locales', () {
      final p = predictionFromJson(predictionJson(p: 0.10, banda: 'ambigua'));
      expect(p.confidence, PredictionConfidence.ambigua);
    });

    test('el caso mapea vistas a/b, notas y URL firmadas (I3, I4, I5)', () {
      final c = caseFromJson(
        caseJson(
          estado: 'PENDIENTE_VALIDACION',
          prediccion: predictionJson(),
          urls: {'a': 'http://x/a', 'b': 'http://x/b'},
        ),
        localPaths: {ImageView.foto1: '/fotos/a.jpg'},
      );
      expect(c.status, CaseStatus.pendienteValidacion);
      expect(c.uidMedico, isNull);
      expect(c.foto1.remoteUrl, 'http://x/a');
      expect(c.foto1.localPath, '/fotos/a.jpg');
      expect(c.foto2.remoteUrl, 'http://x/b');
      expect(c.clinicalData.tiempoAparicion, OnsetTime.entre3y12Meses);
      expect(c.clinicalData.sintomas, {Symptom.picor, Symptom.cambioColor});
      expect(c.internalNotes.single.text, 'Revisar en 3 meses');
      expect(c.analysisAttempts, 1);
      expect(c.prediction!.clasePredicha, LesionClass.melanoma);
    });

    test('los datos clínicos se envían con los valores del backend', () {
      final json = clinicalDataToJson(const ClinicalData(
        ubicacionLesion: ' Espalda ',
        tiempoAparicion: OnsetTime.masDe1Anio,
        sintomas: {Symptom.cambioTamano},
      ));
      expect(json, {
        'ubicacion_lesion': 'Espalda',
        'tiempo_aparicion': 'mas_de_1_anio',
        'sintomas': ['cambio_tamano'],
      });
    });

    test('la validación conserva la predicción original (I8, RF-04.2)', () {
      final v = validationFromJson(validationJson());
      expect(v.decision, ValidationDecision.corregir);
      expect(v.claseFinal, LesionClass.noMelanoma);
      expect(v.prediccionOriginal.clasePredicha, LesionClass.melanoma);
      expect(v.uidEspecialista, isNull);
      expect(v.reportConclusion, 'Lesión no compatible con melanoma');
    });

    test('el informe trae los campos nuevos del backend (I9)', () {
      final d = reportDocumentFromJson(reportDocumentJson(), foto1Path: '/a.jpg');
      expect(d.conclusion, 'Lesión no compatible con melanoma.');
      expect(d.fechaNacimiento, DateTime(1970, 5, 2));
      expect(d.sustentoClinico, 'Patrón reticular regular.');
      expect(d.foto1Path, '/a.jpg');
      expect(reportFromDocumentJson(reportDocumentJson()).conductaClinica, 'Control en 6 meses.');
    });

    test('la bitácora omite los tipos de evento desconocidos (I10)', () {
      final ok = auditEventFromJson({
        'id': 'e1',
        'tipo': 'cambio_permisos',
        'referencia': 'x@h.pe',
        'actor_nombre': 'Admin',
        'fecha': '2026-11-19T14:00:00Z',
      });
      expect(ok!.type, AuditType.cambioRol);
      expect(
          auditEventFromJson({
            'id': 'e2',
            'tipo': 'evento_futuro',
            'referencia': '',
            'actor_nombre': '',
            'fecha': '2026-11-19T14:00:00Z',
          }),
          isNull);
    });

    test('los ids del backend se muestran acortados', () {
      expect(Fmt.caseId('a1b2c3d4e5f6a7b8c9d0'), 'CASO-A1B2C3');
      expect(Fmt.caseId('CASO-0201'), 'CASO-0201');
      expect(Fmt.caseId('local-123'), 'En cola');
    });
  });
}
