import 'package:dermavia/app.dart';
import 'package:dermavia/core/theme/app_theme.dart';
import 'package:dermavia/data/mock/seed_data.dart';
import 'package:dermavia/data/remote/backend_config.dart';
import 'package:dermavia/data/remote/local_case_store.dart';
import 'package:dermavia/data/remote/refresh_hub.dart';
import 'package:dermavia/data/remote/remote_connectivity.dart';
import 'package:dermavia/data/remote/token_provider.dart';
import 'package:dermavia/features/auth/auth_widgets.dart';
import 'package:dermavia/providers/repository_providers.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import '../data/remote/fake_firebase_auth.dart';

/// Inicio de sesión y recuperación en modo `nube`, con Firebase simulado
/// (CONEXION_NUBE.md, N6 y N8).
void main() {
  setUpAll(() => AppFonts.useGoogleFonts = false);

  late FakeFirebaseAuth firebase;

  Widget app() => ProviderScope(
        overrides: [
          backendConfigProvider.overrideWithValue(BackendConfig.forMode(BackendMode.nube)),
          tokenProviderProvider.overrideWithValue(FirebaseTokenProvider(firebase)),
          localCaseStoreProvider.overrideWithValue(LocalCaseStore.memory()),
          refreshHubProvider.overrideWithValue(RefreshHub(pollInterval: null)),
          remoteConnectivityProvider
              .overrideWithValue(RemoteConnectivityService(deviceChanges: const Stream.empty())),
        ],
        child: const DermaviaApp(),
      );

  setUp(() => firebase = FakeFirebaseAuth());

  test('la nube usa la API de Cloud Run y tolera el arranque en frío (N3)', () {
    final config = BackendConfig.forMode(BackendMode.nube);
    expect(config.apiUrl, BackendConfig.cloudApiUrl);
    expect(config.requestTimeout, greaterThan(const Duration(seconds: 20)));
    expect(config.usesFirebase, isTrue);
    expect(BackendConfig.forMode(BackendMode.local).apiUrl, BackendConfig.localApiUrl);
    expect(BackendConfig.forMode(BackendMode.local).usesFirebase, isFalse);
  });

  testWidgets('las cuentas de demostración solo completan el correo (N6)', (tester) async {
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.text('Cuentas de demostración'));
    await tester.tap(find.text('Cuentas de demostración'));
    await tester.pumpAndSettle();
    expect(find.text(DemoCredentials.pendingEmail), findsOneWidget);
    expect(find.textContaining(DemoCredentials.specialistPassword), findsNothing);
    expect(find.textContaining(DemoCredentials.adminPassword), findsNothing);

    await tester.tap(find.text(DemoCredentials.specialistEmail));
    await tester.pumpAndSettle();
    final fields = tester.widgetList<TextFormField>(find.byType(TextFormField)).toList();
    expect(fields[0].controller!.text, DemoCredentials.specialistEmail);
    expect(fields[1].controller!.text, isEmpty);
  });

  testWidgets('recuperar la contraseña envía el correo de Firebase (N8)', (tester) async {
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();

    await tester.tap(find.text('¿Olvidaste tu contraseña?'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextFormField).first, 'lramirez@hospital.gob.pe');
    await tester.tap(find.text('Enviar enlace'));
    await tester.pumpAndSettle();

    expect(firebase.resets, ['lramirez@hospital.gob.pe']);
    expect(find.text(kPasswordLinkSent), findsOneWidget);
    expect(find.text('1 hora'), findsOneWidget);
    // El enlace simulado es solo del backend simulado.
    expect(find.text('Abrir enlace recibido'), findsNothing);
  });

  testWidgets('reenviar el enlace espera 60 s (sin llenar la bandeja)', (tester) async {
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();
    await tester.tap(find.text('¿Olvidaste tu contraseña?'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextFormField).first, 'lramirez@hospital.gob.pe');
    await tester.tap(find.text('Enviar enlace'));
    await tester.pumpAndSettle();

    expect(find.text('Reenviar enlace en 60 s'), findsOneWidget);
    await tester.tap(find.text('Reenviar enlace en 60 s'));
    await tester.pump();
    expect(firebase.resets, hasLength(1));

    await tester.pump(const Duration(seconds: 59));
    expect(find.text('Reenviar enlace en 1 s'), findsOneWidget);
    await tester.pump(const Duration(seconds: 1));
    expect(find.text('Reenviar enlace'), findsOneWidget);
  });

  testWidgets('"Tengo un enlace de activación" pide un enlace nuevo (N8)', (tester) async {
    await tester.pumpWidget(app());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Tengo un enlace de activación'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField).last, DemoCredentials.pendingEmail);
    await tester.tap(find.text('Enviar enlace'));
    await tester.pumpAndSettle();

    expect(firebase.resets, [DemoCredentials.pendingEmail]);
    expect(find.text(kPasswordLinkSent), findsOneWidget);
  });
}
