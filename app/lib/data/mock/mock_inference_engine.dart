import 'dart:math';

import '../../domain/models/clinical_case.dart';
import '../../domain/models/prediction.dart';

/// Parámetros del artefacto versionado que carga el módulo Inferencia
/// (sección 3.4 y EXP-04 de la memoria): modelo de dos fotos con fusión
/// aprendida en float16, calibración isotónica y umbral operativo.
abstract final class ModelArtifact {
  static const version = 'mnv3l-fusion-2v-fp16 v1';

  /// Umbral operativo expresado como probabilidad calibrada (0.070).
  static const operationalThreshold = 0.070;
}

/// Simula al módulo Inferencia del backend. Devuelve una probabilidad
/// calibrada determinista a partir del caso, de modo que la demo sea
/// reproducible. No es un clasificador real: el modelo se ejecuta siempre
/// en el backend desplegado en Cloud Run.
class MockInferenceEngine {
  MockInferenceEngine({this.failingCaseIds = const {}});

  /// Casos cuyo primer análisis falla (para demostrar ERROR_ANALISIS).
  final Set<String> failingCaseIds;
  final _failedOnce = <String>{};

  Prediction predict(ClinicalCase c, DateTime now) {
    if (failingCaseIds.contains(c.id) && _failedOnce.add(c.id)) {
      throw StateError('Fallo simulado del servicio de inferencia');
    }
    final seed = Object.hash(
      c.id,
      c.panoramica.localPath ?? '',
      c.acercamiento.localPath ?? '',
      c.clinicalData.ubicacionLesion,
    );
    final rnd = Random(seed);
    final bucket = rnd.nextDouble();
    double p;
    if (bucket < 0.30) {
      p = 0.70 + rnd.nextDouble() * 0.25; // alta
    } else if (bucket < 0.60) {
      p = 0.30 + rnd.nextDouble() * 0.40; // ambigua
    } else if (bucket < 0.75) {
      p = 0.08 + rnd.nextDouble() * 0.20; // baja
    } else {
      p = 0.01 + rnd.nextDouble() * 0.05; // bajo el umbral
    }
    return predictionFor(p, now);
  }

  static Prediction predictionFor(double p, DateTime at) => Prediction(
        probabilidadMalignidad: p,
        clasePredicha: p >= ModelArtifact.operationalThreshold
            ? LesionClass.maligno
            : LesionClass.benigno,
        versionModelo: ModelArtifact.version,
        umbralOperativo: ModelArtifact.operationalThreshold,
        fechaInferencia: at,
      );
}
