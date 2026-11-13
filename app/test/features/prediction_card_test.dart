import 'package:dermavia/data/mock/mock_inference_engine.dart';
import 'package:dermavia/features/case_review/case_detail_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('la tarjeta usa lenguaje clínico y explica cómo leerla', (tester) async {
    final p = MockInferenceEngine.predictionFor(0.09, DateTime(2026, 10, 29));
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Padding(padding: const EdgeInsets.all(18), child: PredictionCard(prediction: p)),
      ),
    ));

    expect(find.text('Posible melanoma'), findsOneWidget);
    expect(find.text('9%'), findsOneWidget);
    expect(find.text('▲ Alerta desde 7%'), findsOneWidget);
    expect(find.textContaining('calibrada'), findsNothing);
    expect(find.textContaining('umbral'), findsNothing);

    await tester.tap(find.text('¿Cómo leer este resultado?'));
    await tester.pumpAndSettle();
    expect(find.text('Línea de alerta: 7%'), findsOneWidget);
    expect(find.textContaining('gran mayoría de los melanomas'), findsOneWidget);
  });
}
