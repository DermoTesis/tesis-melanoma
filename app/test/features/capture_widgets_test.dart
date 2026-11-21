import 'package:dermavia/domain/models/clinical_case.dart';
import 'package:dermavia/features/capture/capture_widgets.dart';
import 'package:dermavia/features/capture/clinical_data_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('la captura pide dos fotos de la misma lesión, sin panorámica (RF-02.1)',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => Column(
            children: [
              const CaptureSteps(current: ImageView.foto2, firstDone: true),
              TextButton(
                onPressed: () => showCaptureGuide(context, ImageView.foto2),
                child: const Text('Guía'),
              ),
            ],
          ),
        ),
      ),
    ));

    expect(find.text('✓ Foto 1'), findsOneWidget);
    expect(find.text('2 · Foto 2'), findsOneWidget);

    await tester.tap(find.text('Guía'));
    await tester.pumpAndSettle();
    expect(find.text('Foto 2 · Misma lesión, otra toma'), findsOneWidget);
    expect(find.text('Es la misma lesión de la foto 1.'), findsOneWidget);
    expect(find.textContaining('anorámica'), findsNothing);
  });

  test('la lista de ubicaciones no ofrece la región subungueal (D6)', () {
    // HAM10000 excluyó las lesiones subungueales: el sistema no tiene respaldo ahí.
    expect(kBodySites.where((s) => s.toLowerCase().contains('subungue')), isEmpty);
    expect(kBodySites, contains('Otra ubicación'));
  });
}
