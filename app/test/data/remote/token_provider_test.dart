import 'package:dermavia/core/errors/app_exception.dart';
import 'package:dermavia/data/remote/api_client.dart';
import 'package:dermavia/data/remote/token_provider.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_firebase_auth.dart';

void main() {
  late FakeFirebaseAuth firebase;
  late FirebaseTokenProvider tokens;

  setUp(() {
    firebase = FakeFirebaseAuth();
    tokens = FirebaseTokenProvider(firebase);
  });

  group('Inicio de sesión con Firebase (I13, N4)', () {
    test('devuelve el uid y entrega el ID token de la sesión', () async {
      expect(await tokens.signIn(' lramirez@hospital.gob.pe ', 'clave'), 'uid-lramirez');
      expect(await tokens.token(), 'token-de-uid-lramirez');
      await tokens.signOut();
      expect(await tokens.token(), isNull);
    });

    for (final code in [
      'invalid-credential',
      'wrong-password',
      'user-not-found',
      'invalid-email',
      'user-disabled',
    ]) {
      test('$code recibe el error genérico (HU04·CA2)', () async {
        firebase.signInError = code;
        await expectLater(tokens.signIn('a@h.pe', 'x'), throwsA(isA<AuthException>()));
      });
    }

    test('sin correo o sin contraseña no se llama a Firebase', () async {
      firebase.signInError = 'internal-error';
      await expectLater(tokens.signIn('', 'x'), throwsA(isA<AuthException>()));
      await expectLater(tokens.signIn('a@h.pe', ''), throwsA(isA<AuthException>()));
    });

    test('demasiados intentos pide esperar', () async {
      firebase.signInError = 'too-many-requests';
      await expectLater(
          tokens.signIn('a@h.pe', 'x'),
          throwsA(isA<AppException>().having(
              (e) => e.message, 'message', FirebaseTokenProvider.tooManyRequestsMessage)));
    });

    test('sin red es el mismo error de conexión que el de la API (I12, I21)', () async {
      firebase.signInError = 'network-request-failed';
      await expectLater(tokens.signIn('a@h.pe', 'x'), throwsA(isA<NetworkException>()));
    });

    test('otro error de Firebase no se presenta como contraseña incorrecta', () async {
      firebase.signInError = 'internal-error';
      await expectLater(
          tokens.signIn('a@h.pe', 'x'),
          throwsA(isA<AppException>()
              .having((e) => e is AuthException, 'genérico', isFalse)
              .having((e) => e.code, 'code', 'auth/internal-error')));
    });
  });

  group('Renovación del token', () {
    test('si falla (sesiones revocadas por el administrador) devuelve null', () async {
      await tokens.signIn('lramirez@h.pe', 'clave');
      firebase.tokenError = 'user-token-expired';
      expect(await tokens.token(), isNull);
    });

    test('sin red avisa que no hay conexión en vez de cerrar la sesión', () async {
      await tokens.signIn('lramirez@h.pe', 'clave');
      firebase.tokenError = 'network-request-failed';
      await expectLater(tokens.token(), throwsA(isA<NetworkException>()));
    });
  });

  group('Enlace para definir la contraseña (I15, I16)', () {
    test('pide a Firebase el correo de restablecimiento', () async {
      await tokens.sendPasswordLink(' psalas@hospital.gob.pe ');
      expect(firebase.resets, ['psalas@hospital.gob.pe']);
    });

    test('responde igual si la cuenta no existe (HU04·CA2)', () async {
      firebase.resetError = 'user-not-found';
      await tokens.sendPasswordLink('nadie@h.pe');
      firebase.resetError = 'invalid-email';
      await tokens.sendPasswordLink('no-es-correo');
    });

    test('sin red o con demasiados intentos avisa el motivo', () async {
      firebase.resetError = 'network-request-failed';
      await expectLater(tokens.sendPasswordLink('a@h.pe'), throwsA(isA<NetworkException>()));
      firebase.resetError = 'too-many-requests';
      await expectLater(
          tokens.sendPasswordLink('a@h.pe'),
          throwsA(isA<AppException>().having((e) => e.code, 'code', 'too-many-requests')));
    });
  });
}
