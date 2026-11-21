import 'package:dermavia/data/mock/mock_inference_engine.dart';
import 'package:dermavia/domain/models/clinical_case.dart';
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

    test('sin alerta no se muestra porcentaje ni un nivel de riesgo', () {
      final p = noAlert(0.0699);
      expect(p.headline, 'Sin alerta de melanoma');
      expect(p.shortSummary, 'Sin alerta de melanoma');
      expect(p.riskLevel, isNull);
      expect(p.riskLabel, 'Por debajo de la línea de alerta');
      expect(p.frequencyText, isNull);
      expect(p.confidence, PredictionConfidence.sinAlerta);
    });

    test('sin alerta se advierte que no descarta un melanoma', () {
      expect(noAlert(0.03).contextText,
          contains('1 de cada 11 melanomas quedó por debajo de la línea de alerta'));
      expect(alert(0.09).contextText, contains('unas 7 de cada 10 alertas no fueron melanoma'));
      expect(Prediction.scopeText, contains('carcinoma basocelular'));
    });

    test('el nivel de riesgo sigue los tramos de la predicción', () {
      expect(alert(0.45).riskLabel, 'Riesgo intermedio');
      expect(alert(0.82).riskLabel, 'Riesgo alto');
    });

    test('el riesgo mostrado tiene piso y techo', () {
      expect(noAlert(0.0).riskText, '< 3%');
      expect(alert(0.0699).riskText, '7%');
      expect(alert(0.913).riskText, '> 90%');
      expect(alert(1.0).shortSummary, 'Posible melanoma · riesgo > 90%');
    });

    test('la frecuencia natural se ata al conjunto de desarrollo', () {
      expect(alert(0.30).frequencyText,
          'En las lesiones con las que se desarrolló el sistema, unas 30 de cada 100 '
          'con este resultado fueron melanoma.');
      expect(alert(1.0).frequencyText, contains('más de 90 de cada 100'));
    });
  });

  group('Ubicaciones fuera del dominio del modelo (A10)', () {
    test('avisa en la región subungueal y en palmas y plantas', () {
      expect(siteNoticeFor('Región subungueal'), contains('sin lesiones subungueales'));
      expect(siteNoticeFor('Planta del pie derecho'), contains('palma o la planta'));
      expect(siteNoticeFor('Mano izquierda'), contains('palma o la planta'));
      expect(siteNoticeFor('Espalda, región escapular'), isNull);
    });
  });
}
