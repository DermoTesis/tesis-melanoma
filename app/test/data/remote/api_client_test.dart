import 'dart:convert';

import 'package:dermavia/core/errors/app_exception.dart';
import 'package:dermavia/data/remote/api_client.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

http.Response _error(int status, String codigo, String mensaje) => http.Response(
      jsonEncode({
        'error': {'codigo': codigo, 'mensaje': mensaje}
      }),
      status,
      headers: {'content-type': 'application/json; charset=utf-8'},
    );

void main() {
  group('ApiClient (I12)', () {
    test('agrega el token y decodifica JSON en UTF-8', () async {
      late http.Request seen;
      final api = ApiClient(
        baseUrl: 'http://srv/',
        token: () async => 'dev:especialista-dev',
        client: MockClient((r) async {
          seen = r;
          return http.Response.bytes(utf8.encode('{"nombres": "María"}'), 200);
        }),
      );
      final json = await api.get('/users/me');
      expect(seen.url.toString(), 'http://srv/users/me');
      expect(seen.headers['Authorization'], 'Bearer dev:especialista-dev');
      expect(json['nombres'], 'María');
    });

    Future<Object?> failWith(http.Response response, {void Function()? onUnauth}) async {
      final api = ApiClient(
        baseUrl: 'http://srv',
        token: () async => null,
        client: MockClient((_) async => response),
        onUnauthenticated: onUnauth,
      );
      try {
        await api.post('/cases', body: {});
      } catch (e) {
        return e;
      }
      return null;
    }

    test('los códigos del backend se traducen a las excepciones de la app', () async {
      expect(await failWith(_error(409, 'consent-required', 'x')), isA<ConsentRequiredException>());
      expect(await failWith(_error(409, 'validation-required', 'x')),
          isA<ValidationRequiredException>());
      final denied = await failWith(_error(403, 'permission-denied', 'Sin acceso clínico.'));
      expect(denied, isA<PermissionDeniedException>());
      expect((denied as AppException).message, 'Sin acceso clínico.');
      final state = await failWith(_error(409, 'invalid-state', 'Ya no se puede.')) as AppException;
      expect(state.code, 'invalid-state');
      expect(state.message, 'Ya no se puede.');
    });

    test('un 401 avisa que la sesión expiró', () async {
      var called = false;
      final e = await failWith(_error(401, 'unauthenticated', 'Tu sesión expiró.'),
          onUnauth: () => called = true) as AppException;
      expect(e.code, 'unauthenticated');
      expect(called, isTrue);
    });

    test('un fallo de red es NetworkException y marca el servidor inalcanzable', () async {
      final reach = <bool>[];
      final api = ApiClient(
        baseUrl: 'http://srv',
        token: () async => null,
        client: MockClient((_) async => throw http.ClientException('sin red')),
        onReachability: reach.add,
      );
      await expectLater(api.get('/cases'), throwsA(isA<NetworkException>()));
      expect(reach, [false]);
    });

    test('un 500 sin cuerpo JSON da un mensaje genérico', () async {
      final e = await failWith(http.Response('Internal Server Error', 500)) as AppException;
      expect(e.code, 'internal');
    });
  });
}
