import 'package:dermavia/app.dart';
import 'package:dermavia/core/theme/app_theme.dart';
import 'package:dermavia/data/mock/mock_backend.dart';
import 'package:dermavia/data/mock/seed_data.dart';
import 'package:dermavia/providers/repository_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  setUpAll(() => AppFonts.useGoogleFonts = false);

  Widget app(MockBackend backend) => ProviderScope(
        overrides: [mockBackendProvider.overrideWithValue(backend)],
        child: const DermaviaApp(),
      );

  MockBackend backend() => MockBackend(
        latency: Duration.zero,
        analysisDuration: Duration.zero,
        schedulerInterval: null,
      );

  testWidgets('credenciales incorrectas muestran un error genérico', (tester) async {
    final b = backend();
    addTearDown(b.dispose);
    await tester.pumpWidget(app(b));
    await tester.pumpAndSettle();

    expect(find.text('Iniciar sesión'), findsOneWidget);
    await tester.enterText(find.byType(TextFormField).at(0), DemoCredentials.specialistEmail);
    await tester.enterText(find.byType(TextFormField).at(1), 'incorrecta');
    await tester.tap(find.text('Iniciar sesión'));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('login-error')), findsOneWidget);
    expect(find.textContaining('Correo o contraseña incorrectos'), findsOneWidget);
  });

  testWidgets('el especialista llega a su panel de casos', (tester) async {
    final b = backend();
    addTearDown(b.dispose);
    await tester.pumpWidget(app(b));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextFormField).at(0), DemoCredentials.specialistEmail);
    await tester.enterText(
        find.byType(TextFormField).at(1), DemoCredentials.specialistPassword);
    await tester.tap(find.text('Iniciar sesión'));
    await tester.pumpAndSettle();

    expect(find.text('Mis casos'), findsOneWidget);
    expect(find.text('María Quispe H.'), findsOneWidget);
  });
}
