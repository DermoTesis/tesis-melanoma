import 'package:dermavia/data/mock/mock_inference_engine.dart';
import 'package:dermavia/domain/models/prediction.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final at = DateTime(2026, 10, 29);
  // La clase la decide el backend; en estas pruebas solo importa el texto.
  Prediction alert(double p) =>
      MockInferenceEngine.predictionFor(p, at, clase: LesionClass.melanoma);
  Prediction noAlert(double p) =>
      MockInferenceEngine.predictionFor(p, at, clase: LesionClass.noMelanoma);

  group('Textos para el médico', () {
    test('una alerta se presenta como posible melanoma con su riesgo', () {
      final p = alert(0.09);
      expect(p.headline, 'Posible melanoma');
      expect(p.shortSummary, 'Posible melanoma · riesgo 9%');
      expect(p.riskLabel, 'Riesgo bajo');
      expect(p.alertPercent, 7);
    });

    test('bajo la línea de alerta no se habla de malignidad', () {
      final p = noAlert(0.03);
      expect(p.headline, 'Sin alerta de melanoma');
      expect(p.riskLabel, 'Riesgo muy bajo');
    });

    test('el nivel de riesgo sigue los tramos de la predicción', () {
      expect(alert(0.45).riskLabel, 'Riesgo intermedio');
      expect(alert(0.82).riskLabel, 'Riesgo alto');
    });

    test('la probabilidad se expresa como frecuencia natural', () {
      expect(alert(0.30).frequencyText,
          'Unas 30 de cada 100 lesiones con este resultado son melanoma.');
      expect(noAlert(0.004).frequencyText,
          'Menos de 1 de cada 100 lesiones con este resultado son melanoma.');
    });
  });
}
