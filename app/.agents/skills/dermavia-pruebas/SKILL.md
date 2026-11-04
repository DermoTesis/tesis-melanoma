---
name: dermavia-pruebas
description: Convenciones para escribir y ejecutar pruebas unitarias y de widget en Dermavía (MockBackend sin latencia, ProviderScope con overrides, DemoCredentials, fuentes desactivadas, nombres en español con HU/RF) y comandos de verificación (flutter analyze, flutter test, flutter build apk). Úsala al añadir pruebas o antes de dar por terminado un cambio.
---

# Pruebas en Dermavía

## Estructura

```
test/
  core/      servicios de lib/core (p. ej. image_quality_service_test.dart)
  data/      reglas de negocio vía repositorios simulados (mock_repositories_test.dart)
  domain/    modelos puros (prediction_test.dart)
  features/  pruebas de widget de pantallas y componentes
```

El archivo de prueba replica la ruta del código: `lib/x/y.dart` → `test/x/y_test.dart`.
Importa siempre con `package:dermavia/...`.

## Nombres

`group` y `test` en español, describiendo el comportamiento y citando el requisito:

```dart
group('Validación', () {
  test('el sustento clínico es obligatorio (RF-04.3)', () async { ... });
});
```

## Pruebas de reglas (repositorios simulados)

```dart
late MockBackend b;
setUp(() {
  b = MockBackend(
    latency: Duration.zero,
    analysisDuration: Duration.zero,
    schedulerInterval: null,   // sin Timer periódico
  );
});
tearDown(() => b.dispose());

Future<void> settle() => Future<void>.delayed(const Duration(milliseconds: 5));
```

- Inicia sesión con `DemoCredentials` (`specialistEmail`/`specialistPassword`,
  `adminEmail`, `revokedEmail`, `pendingEmail`) desde `seed_data.dart`.
- Tras `submitCase` llama a `settle()` para que termine el análisis simulado.
- Paciente sembrado con consentimiento vigente: `'p-jmamani'`.
- Para fijar el resultado del análisis: `MockBackend(inference: MockInferenceEngine(failingCaseIds: {...}))`
  o construye la predicción con `MockInferenceEngine.predictionFor(0.09, fecha)`.
- Para tiempo controlado (vencimientos de 48 h, enlaces de 30 min): pasa
  `clock: () => fecha` al `MockBackend`.
- Errores: `await expectLater(futuro, throwsA(isA<ConsentRequiredException>()))`.
- Cada regla de [`dermavia-reglas-clinicas`](../dermavia-reglas-clinicas/SKILL.md) debe tener al menos una prueba que verifique
  el **rechazo**, no solo el camino feliz.

## Pruebas de widget

App completa:

```dart
setUpAll(() => AppFonts.useGoogleFonts = false); // no descarga fuentes

Widget app(MockBackend backend) => ProviderScope(
      overrides: [mockBackendProvider.overrideWithValue(backend)],
      child: const DermaviaApp(),
    );
```

Componente aislado (si no usa providers):

```dart
await tester.pumpWidget(MaterialApp(
  home: Scaffold(body: PredictionCard(prediction: p)),
));
```

- Usa `pumpAndSettle()` tras taps y navegación; con `analysisDuration` en cero no hay
  temporizadores pendientes.
- Localiza por texto visible (`find.text`, `find.textContaining`) o por `Key` estable
  (`Key('login-error')`). Añade `Key` en el widget si el texto es ambiguo.
- Verifica también lo que **no** debe aparecer (p. ej. `find.textContaining('umbral')`
  → `findsNothing`).

## Verificación antes de terminar

```bash
flutter analyze          # lints de flutter_lints (analysis_options.yaml)
flutter test             # toda la suite
flutter test test/data/mock_repositories_test.dart   # un archivo
flutter test --plain-name "sustento clínico"          # una prueba por nombre
flutter build apk        # solo si cambió android/, pubspec o algo nativo
```

Informa el resultado real: si alguna prueba falla, muestra la salida en vez de
resumirla como éxito.
