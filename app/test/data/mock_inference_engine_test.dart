import 'package:dermavia/data/mock/mock_inference_engine.dart';
import 'package:dermavia/domain/models/prediction.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final at = DateTime(2026, 11, 13);

  group('Artefacto de EXP-04 (RF-03.3)', () {
    test('la calibración reproduce los valores del registro', () {
      expect(ModelArtifact.calibrate(ModelArtifact.decisionThreshold),
          ModelArtifact.calibratedThreshold);
      expect(ModelArtifact.calibrate(0.0), 0.0);
      expect(ModelArtifact.calibrate(0.15), closeTo(0.1752136752136752, 1e-12));
      expect(ModelArtifact.calibrate(1.0), 1.0);
    });

    test('la clase se decide con la salida sin calibrar', () {
      expect(ModelArtifact.classify(ModelArtifact.decisionThreshold), LesionClass.melanoma);
      expect(ModelArtifact.classify(0.0137), LesionClass.noMelanoma);
    });

    test('en el escalón de la calibración, el mismo riesgo puede tener o no alerta', () {
      // Toda salida entre 0.0040 y 0.0193 se calibra a ~7%: la probabilidad
      // calibrada no basta para decidir, por eso la clase viene del backend.
      final over = MockInferenceEngine.fromModelOutput(0.015, at);
      final under = MockInferenceEngine.fromModelOutput(0.010, at);
      expect(over.probabilidadMalignidad, under.probabilidadMalignidad);
      expect(over.percent, 7);
      expect(over.clasePredicha, LesionClass.melanoma);
      expect(under.clasePredicha, LesionClass.noMelanoma);
      // Con el corte antiguo (calibrada >= 0.070) este caso quedaba sin alerta.
      expect(over.probabilidadMalignidad < 0.070, isTrue);
    });

    test('las predicciones simuladas respetan la decisión del artefacto', () {
      // La línea de alerta que se muestra es la del artefacto en todos los casos.
      for (final out in [0.0, 0.003, 0.0137, 0.0138, 0.019, 0.05, 0.3, 0.9]) {
        final p = MockInferenceEngine.fromModelOutput(out, at);
        expect(p.clasePredicha, ModelArtifact.classify(out), reason: 'salida $out');
        expect(p.probabilidadMalignidad, ModelArtifact.calibrate(out));
        expect(p.umbralOperativo, ModelArtifact.calibratedThreshold);
      }
    });
  });
}
