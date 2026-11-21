import 'package:dermavia/data/remote/api_client.dart';
import 'package:dermavia/data/remote/password_link_throttle.dart';
import 'package:dermavia/data/remote/token_provider.dart';
import 'package:flutter_test/flutter_test.dart';

import 'fake_firebase_auth.dart';

void main() {
  late DateTime now;
  late PasswordLinkThrottle throttle;

  setUp(() {
    now = DateTime(2026, 11, 21, 10);
    throttle = PasswordLinkThrottle(clock: () => now);
  });

  group('Límite de envíos del enlace para definir la contraseña', () {
    test('el mismo correo espera 60 s entre enlaces', () {
      throttle.check('lramirez@h.pe');
      throttle.record('lramirez@h.pe');

      now = now.add(const Duration(seconds: 20));
      expect(
          () => throttle.check(' LRamirez@h.pe '),
          throwsA(isA<PasswordLinkCooldownException>()
              .having((e) => e.remaining, 'remaining', const Duration(seconds: 40))
              .having((e) => e.message, 'message', contains('40 s'))));

      now = now.add(const Duration(seconds: 40));
      throttle.check('lramirez@h.pe');
    });

    test('otro correo no espera, pero hay un máximo por dispositivo', () {
      for (var i = 0; i < PasswordLinkThrottle.maxPerWindow; i++) {
        throttle.check('medico$i@h.pe');
        throttle.record('medico$i@h.pe');
      }
      expect(() => throttle.check('otro@h.pe'), throwsA(isA<PasswordLinkCooldownException>()));

      now = now.add(PasswordLinkThrottle.window);
      throttle.check('otro@h.pe');
    });
  });

  group('Con Firebase', () {
    late FakeFirebaseAuth firebase;
    late FirebaseTokenProvider tokens;

    setUp(() {
      firebase = FakeFirebaseAuth();
      tokens = FirebaseTokenProvider(firebase, throttle: throttle);
    });

    test('un segundo enlace inmediato no llega a Firebase', () async {
      await tokens.sendPasswordLink('lramirez@h.pe');
      await expectLater(
          tokens.sendPasswordLink('lramirez@h.pe'), throwsA(isA<PasswordLinkCooldownException>()));
      expect(firebase.resets, ['lramirez@h.pe']);
    });

    test('un envío fallido (sin red) no cuenta: se puede reintentar', () async {
      firebase.resetError = 'network-request-failed';
      await expectLater(tokens.sendPasswordLink('lramirez@h.pe'), throwsA(isA<NetworkException>()));
      firebase.resetError = null;
      await tokens.sendPasswordLink('lramirez@h.pe');
      expect(firebase.resets, ['lramirez@h.pe']);
    });

    test('cuenta igual si el correo no existe, para no revelarlo (HU04·CA2)', () async {
      firebase.resetError = 'user-not-found';
      await tokens.sendPasswordLink('nadie@h.pe');
      await expectLater(
          tokens.sendPasswordLink('nadie@h.pe'), throwsA(isA<PasswordLinkCooldownException>()));
    });
  });
}
