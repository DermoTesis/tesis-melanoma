import 'package:dermavia/data/mock/mock_inference_engine.dart';
import 'package:dermavia/domain/models/prediction.dart';
import 'package:dermavia/features/case_review/case_detail_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Future<void> pumpCard(WidgetTester tester, Prediction p) => tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: Padding(
                padding: const EdgeInsets.all(18), child: PredictionCard(prediction: p)),
          ),
        ),
      ));

  testWidgets('la tarjeta usa lenguaje clínico y explica cómo leerla', (tester) async {
    final p = MockInferenceEngine.predictionFor(0.09, DateTime(2026, 10, 29),
        clase: LesionClass.melanoma);
    await pumpCard(tester, p);

    expect(find.text('Posible melanoma'), findsOneWidget);
    expect(find.text('9%'), findsOneWidget);
    expect(find.text('▲ Alerta desde 7%'), findsOneWidget);
    expect(find.textContaining('carcinoma basocelular'), findsOneWidget);
    expect(find.textContaining('calibrada'), findsNothing);
    expect(find.textContaining('umbral'), findsNothing);
    expect(find.textContaining('Modelo'), findsNothing);

    await tester.tap(find.text('¿Cómo leer este resultado?'));
    await tester.pumpAndSettle();
    expect(find.text('Línea de alerta: 7%'), findsOneWidget);
    expect(find.textContaining('detectó 52 de 57 melanomas'), findsOneWidget);
    expect(find.text('Qué no evalúa'), findsOneWidget);
  });

  testWidgets('sin alerta no muestra el riesgo ni lo califica de bajo (A5, A11)',
      (tester) async {
    // Mismo 7% que una alerta en el escalón de la calibración.
    final p = MockInferenceEngine.fromModelOutput(0.010, DateTime(2026, 10, 29));
    expect(p.percent, 7);
    await pumpCard(tester, p);

    expect(find.text('Sin alerta de melanoma'), findsOneWidget);
    expect(find.text('Por debajo de la línea de alerta'), findsOneWidget);
    expect(find.text('7%'), findsNothing);
    expect(find.text('Riesgo estimado'), findsNothing);
    expect(find.textContaining('muy bajo'), findsNothing);
    expect(find.textContaining('No descarta un melanoma'), findsOneWidget);
    expect(find.textContaining('carcinoma basocelular'), findsOneWidget);
  });
}
