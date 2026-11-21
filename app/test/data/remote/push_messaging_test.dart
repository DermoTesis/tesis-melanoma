import 'dart:async';
import 'dart:convert';

import 'package:dermavia/data/remote/api_client.dart';
import 'package:dermavia/data/remote/push_messaging.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// Cloud Messaging simulado.
class FakePush implements PushMessaging {
  var permission = true;
  var token = 'fcm-1';
  var deleted = 0;
  var deleteFails = false;

  /// Si no es null, `deleteToken` espera a que se complete (red lenta).
  Completer<void>? deleteGate;
  final calls = <String>[];
  final refresh = StreamController<String>.broadcast();

  @override
  Future<bool> requestPermission() async => permission;

  @override
  Future<String?> getToken() async {
    calls.add('getToken');
    return token;
  }

  @override
  Stream<String> get onTokenRefresh => refresh.stream;

  @override
  Future<void> deleteToken() async {
    calls.add('deleteToken');
    await deleteGate?.future;
    if (deleteFails) throw Exception('sin conexión');
    deleted++;
  }

  @override
  Future<Map<String, dynamic>?> initialMessage() async => null;

  @override
  Stream<Map<String, dynamic>> get onMessageOpenedApp => const Stream.empty();

  @override
  Stream<Map<String, dynamic>> get onMessage => const Stream.empty();
}

void main() {
  late List<String> sentTokens;
  late ApiClient api;
  late FakePush push;
  late DeviceRegistration devices;

  setUp(() {
    sentTokens = [];
    api = ApiClient(
      baseUrl: 'http://srv',
      token: () async => 't',
      client: MockClient((r) async {
        if (r.method == 'POST' && r.url.path == '/users/me/devices') {
          sentTokens.add((jsonDecode(r.body) as Map)['token'] as String);
          return http.Response('', 204);
        }
        return http.Response('', 404);
      }),
    );
    push = FakePush();
    devices = DeviceRegistration(api, push);
  });

  tearDown(() => devices.dispose());

  group('Registro del dispositivo para las alertas (I22, N9)', () {
    test('tras el login manda el token y lo vuelve a mandar si cambia', () async {
      await devices.register();
      expect(sentTokens, ['fcm-1']);
      push.refresh.add('fcm-2');
      await Future<void>.delayed(Duration.zero);
      await Future<void>.delayed(Duration.zero);
      expect(sentTokens, ['fcm-1', 'fcm-2']);
    });

    test('sin permiso de notificaciones no registra nada', () async {
      push.permission = false;
      await devices.register();
      expect(sentTokens, isEmpty);
    });

    test('al cerrar sesión borra el token y deja de seguir sus cambios', () async {
      await devices.register();
      push.deleted = 0;
      await devices.unregister();
      expect(push.deleted, 1);
      push.refresh.add('fcm-3');
      await Future<void>.delayed(Duration.zero);
      expect(sentTokens, ['fcm-1']);
    });
  });

  group('Token de la sesión anterior (N5, N9)', () {
    test('al abrir la app se borra el token que quedó de la última vez', () async {
      await devices.clearStaleToken();
      expect(push.deleted, 1);
      // Ya borrado: el login no lo vuelve a borrar.
      await devices.register();
      expect(push.calls, ['deleteToken', 'getToken']);
    });

    test('si el login llega mientras se borra, espera antes de pedir el token', () async {
      push.deleteGate = Completer<void>();
      final clearing = devices.clearStaleToken();
      final registering = devices.register();
      await Future<void>.delayed(Duration.zero);
      expect(push.calls, ['deleteToken'], reason: 'no debe pedir el token viejo');
      push.deleteGate!.complete();
      await clearing;
      await registering;
      expect(push.calls, ['deleteToken', 'getToken']);
      expect(sentTokens, ['fcm-1']);
    });

    test('si al abrir no hubo conexión, lo reintenta antes de registrar', () async {
      push.deleteFails = true;
      await devices.clearStaleToken();
      expect(push.deleted, 0);
      push.deleteFails = false;
      await devices.register();
      expect(push.calls, ['deleteToken', 'deleteToken', 'getToken']);
      expect(push.deleted, 1);
    });
  });
}
