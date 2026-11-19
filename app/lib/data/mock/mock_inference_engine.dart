import 'dart:math';

import '../../domain/models/clinical_case.dart';
import '../../domain/models/prediction.dart';

/// Parámetros del artefacto versionado que carga el módulo Inferencia
/// (sección 3.4 y EXP-04 de la memoria): modelo de dos fotos con fusión
/// aprendida en float16, calibración isotónica y umbral operativo.
///
/// Copiados de `resultados/exp04/20261004T172732Z_registro/registro.json`
/// (clave `artifact`). La decisión se toma con la salida **sin calibrar**
/// del modelo; la calibración solo cambia el número que ve el médico. Las dos
/// cosas no son intercambiables: la isotónica tiene un escalón que cruza el
/// umbral (toda salida entre 0.0040 y 0.0193 se calibra a 0.0699), así que
/// ningún corte sobre la probabilidad calibrada reproduce la decisión.
abstract final class ModelArtifact {
  static const version = '20261004T172732Z_registro';

  /// Umbral de decisión sobre la salida sin calibrar: "melanoma" si la salida
  /// es >= este valor. Asegura sensibilidad >= 90% con 95% de confianza en
  /// la validación (EXP-04).
  static const decisionThreshold = 0.013780074194073677;

  /// El umbral de decisión expresado como probabilidad calibrada (~0.070).
  /// Solo se usa para mostrar la "línea de alerta"; no decide la clase.
  static const calibratedThreshold = 0.06993006993006994;

  // Nodos de la calibración isotónica (x: salida sin calibrar, y: calibrada).
  static const _calibrationX = <double>[
    1.7400475371687207e-07, 0.0001325082703260705, 0.00013504941307473928,
    0.003998605068773031, 0.004043735098093748, 0.019288774579763412,
    0.019368181005120277, 0.04918146878480911, 0.04924832656979561,
    0.06731300801038742, 0.06748652458190918, 0.08758735656738281,
    0.0877312570810318, 0.21303842961788177, 0.21307289600372314,
    0.2211335152387619, 0.22135035693645477, 0.22911539673805237,
    0.22971779108047485, 0.24788935482501984, 0.24838505685329437,
    0.28487613797187805, 0.28607165813446045, 0.38363248109817505,
    0.38370850682258606, 0.5354464054107666, 0.5355275869369507,
    0.6217862367630005, 0.6250860691070557, 0.776891827583313,
    0.779879093170166, 0.8177807331085205, 0.8200851082801819,
    0.974137008190155, 0.9760978817939758, 0.9963585734367371,
    0.9977256059646606,
  ];
  static const _calibrationY = <double>[
    0.0, 0.0, 0.027888446215139442,
    0.027888446215139442, 0.06993006993006994, 0.06993006993006994,
    0.07627118644067797, 0.07627118644067797, 0.08860759493670886,
    0.08860759493670886, 0.1411764705882353, 0.1411764705882353,
    0.1752136752136752, 0.1752136752136752, 0.2,
    0.2, 0.25, 0.25,
    0.2631578947368421, 0.2631578947368421, 0.3333333333333333,
    0.3333333333333333, 0.3492063492063492, 0.3492063492063492,
    0.4375, 0.4375, 0.4444444444444444,
    0.4444444444444444, 0.5789473684210527, 0.5789473684210527,
    0.6363636363636364, 0.6363636363636364, 0.7468354430379747,
    0.7468354430379747, 0.9130434782608695, 0.9130434782608695,
    1.0,
  ];

  /// Clase predicha a partir de la salida sin calibrar, como en el backend.
  static LesionClass classify(double modelOutput) =>
      modelOutput >= decisionThreshold ? LesionClass.melanoma : LesionClass.noMelanoma;

  /// Probabilidad calibrada: interpolación lineal entre los nodos, recortada
  /// en los extremos (igual que `numpy.interp` en `melanoma.calibration.apply`).
  static double calibrate(double modelOutput) {
    const xs = _calibrationX, ys = _calibrationY;
    if (modelOutput <= xs.first) return ys.first;
    if (modelOutput >= xs.last) return ys.last;
    var i = 0;
    while (xs[i + 1] < modelOutput) {
      i++;
    }
    final x0 = xs[i], x1 = xs[i + 1];
    return ys[i] + (ys[i + 1] - ys[i]) * (modelOutput - x0) / (x1 - x0);
  }
}

/// Simula al módulo Inferencia del backend. Genera una salida sin calibrar
/// determinista a partir del caso, de modo que la demo sea reproducible, y le
/// aplica el artefacto igual que el backend: decide con la salida sin
/// calibrar y calibra solo lo que se muestra. No es un clasificador real: el
/// modelo se ejecuta siempre en el backend desplegado en Cloud Run.
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
      c.foto1.localPath ?? '',
      c.foto2.localPath ?? '',
      c.clinicalData.ubicacionLesion,
    );
    final rnd = Random(seed);
    // Tramos de la salida sin calibrar, ilustrativos (no siguen la
    // distribución real de la validación).
    final bucket = rnd.nextDouble();
    double out;
    if (bucket < 0.30) {
      out = 0.82 + rnd.nextDouble() * 0.175; // riesgo alto (75–91%)
    } else if (bucket < 0.60) {
      out = 0.25 + rnd.nextDouble() * 0.55; // intermedio (33–64%)
    } else if (bucket < 0.75) {
      out = ModelArtifact.decisionThreshold + rnd.nextDouble() * 0.2; // bajo, con alerta
    } else {
      out = rnd.nextDouble() * ModelArtifact.decisionThreshold; // sin alerta
    }
    return fromModelOutput(out, now);
  }

  /// La predicción que devolvería el backend para una salida sin calibrar.
  static Prediction fromModelOutput(double modelOutput, DateTime at) => predictionFor(
        ModelArtifact.calibrate(modelOutput),
        at,
        clase: ModelArtifact.classify(modelOutput),
      );

  /// Una predicción con la probabilidad calibrada y la clase dadas, como
  /// llegan del backend. La clase no se deduce de la probabilidad calibrada:
  /// la decide el backend con la salida sin calibrar.
  static Prediction predictionFor(double p, DateTime at, {required LesionClass clase}) =>
      Prediction(
        probabilidadMalignidad: p,
        clasePredicha: clase,
        versionModelo: ModelArtifact.version,
        umbralOperativo: ModelArtifact.calibratedThreshold,
        fechaInferencia: at,
      );
}
