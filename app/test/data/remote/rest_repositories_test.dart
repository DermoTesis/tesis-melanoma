import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:dermavia/core/errors/app_exception.dart';
import 'package:dermavia/data/remote/api_client.dart';
import 'package:dermavia/data/remote/local_case_store.dart';
import 'package:dermavia/data/remote/refresh_hub.dart';
import 'package:dermavia/data/remote/rest_repositories.dart';
import 'package:dermavia/data/remote/token_provider.dart';
import 'package:dermavia/domain/models/clinical_case.dart';
import 'package:dermavia/domain/models/prediction.dart';
import 'package:dermavia/domain/models/validation.dart';
import 'package:dermavia/domain/repositories/repositories.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'fixtures.dart';

/// Conectividad controlada por la prueba.
class FakeConnectivity implements ConnectivityService {
  FakeConnectivity({this.online = true});
  bool online;
  final _changes = StreamController<bool>.broadcast();

  @override
  bool get isOnline => online;

  @override
  Stream<bool> onlineChanges() => _changes.stream;

  @override
  void setOnline(bool value) {
    online = value;
    _changes.add(value);
  }
}

/// Backend de prueba: registra las peticiones y responde por ruta.
class FakeServer {
  final requests = <http.Request>[];
  var networkDown = false;
  var revoked = false;
  var caseState = 'REGISTRADO';

  List<String> get calls => [for (final r in requests) '${r.method} ${r.url.path}'];

  http.Response _json(Object body, [int status = 200]) => http.Response.bytes(
      utf8.encode(jsonEncode(body)), status,
      headers: {'content-type': 'application/json; charset=utf-8'});

  late final client = MockClient((r) async {
    if (networkDown) throw http.ClientException('sin red');
    requests.add(r);
    final path = r.url.path;
    switch ('${r.method} $path') {
      case 'GET /users/me':
        return _json(userJson(accesoClinico: !revoked));
      case 'POST /cases':
        return _json(caseJson(estado: caseState), 201);
      case 'POST /cases/a1b2c3d4e5f6a7b8c9d0/upload-url':
        final vista = (jsonDecode(r.body) as Map)['vista'];
        return _json({
          'url': 'http://almacen/casos/a1b2c3d4e5f6a7b8c9d0/$vista?firma=x',
          'metodo': 'PUT',
          'encabezados': {'Content-Type': 'image/jpeg'},
          'ruta': 'casos/a1b2c3d4e5f6a7b8c9d0/$vista',
          'vence': '2026-11-19T14:30:00Z',
        });
      case 'POST /cases/a1b2c3d4e5f6a7b8c9d0/submit':
        caseState = 'PENDIENTE_VALIDACION';
        return _json(caseJson(estado: caseState, prediccion: predictionJson()));
      case 'GET /cases/a1b2c3d4e5f6a7b8c9d0':
        return _json(caseJson(
            estado: caseState,
            prediccion: caseState == 'REGISTRADO' ? null : predictionJson(),
            urls: {'a': 'http://almacen/a', 'b': 'http://almacen/b'}));
      case 'GET /cases':
        return _json([caseJson(estado: caseState)]);
      case 'POST /validations':
        return _json(validationJson(), 201);
    }
    if (r.method == 'PUT' && r.url.host == 'almacen') return http.Response('', 200);
    return _json({
      'error': {'codigo': 'not-found', 'mensaje': 'No encontrado'}
    }, 404);
  });
}

void main() {
  late FakeServer server;
  late DevTokenProvider tokens;
  late ApiClient api;
  late RefreshHub hub;
  late LocalCaseStore store;
  late FakeConnectivity connectivity;
  late RestCaseRepository cases;
  late Directory dir;
  late CaseDraft draft;
  const data = ClinicalData(ubicacionLesion: 'Brazo derecho', tiempoAparicion: OnsetTime.noSabe);

  Future<void> settle() => Future<void>.delayed(const Duration(milliseconds: 20));

  setUp(() async {
    server = FakeServer();
    tokens = DevTokenProvider();
    api = ApiClient(baseUrl: 'http://srv', token: tokens.token, client: server.client);
    hub = RefreshHub(pollInterval: null);
    store = LocalCaseStore.memory();
    connectivity = FakeConnectivity();
    cases = RestCaseRepository(api, hub, store, connectivity);
    dir = await Directory.systemTemp.createTemp('dermavia_test');
    CaseImage image(ImageView v) {
      final f = File('${dir.path}/${v.name}.jpg')..writeAsBytesSync([0xFF, 0xD8, 0xFF]);
      return CaseImage(view: v, source: CaptureSource.camara, localPath: f.path);
    }

    draft = CaseDraft(
      patientId: 'pac1',
      foto1: image(ImageView.foto1),
      foto2: image(ImageView.foto2),
    );
    await tokens.signIn(DevAccounts.specialistEmail, 'dev');
  });

  tearDown(() async {
    cases.dispose();
    hub.dispose();
    await dir.delete(recursive: true);
  });

  group('Inicio de sesión con el servidor local (I13, I14)', () {
    test('usa el token dev:<uid> y carga el perfil', () async {
      final auth = RestAuthRepository(api, DevTokenProvider());
      final user = await auth.signIn(DevAccounts.specialistEmail, 'dev');
      expect(user.uid, 'especialista-dev');
      expect(auth.currentUser, isNotNull);
      expect(server.requests.last.headers['Authorization'], 'Bearer dev:especialista-dev');
    });

    test('un correo desconocido recibe el error genérico (HU04·CA2)', () async {
      final auth = RestAuthRepository(api, DevTokenProvider());
      await expectLater(auth.signIn('otro@h.pe', 'dev'), throwsA(isA<AuthException>()));
    });

    test('un especialista con el acceso revocado no entra (RF-01.4)', () async {
      server.revoked = true;
      final auth = RestAuthRepository(api, DevTokenProvider());
      await expectLater(auth.signIn(DevAccounts.specialistEmail, 'dev'),
          throwsA(isA<PermissionDeniedException>()));
      expect(auth.currentUser, isNull);
    });
  });

  group('Envío del caso (I17, I19)', () {
    test('registra, sube las dos fotos y analiza sin bloquear', () async {
      final c = await cases.submitCase(draft, data);
      expect(c.status, CaseStatus.registrado);
      expect(c.id, 'a1b2c3d4e5f6a7b8c9d0');
      await settle();
      expect(server.calls, [
        'POST /cases',
        'POST /cases/a1b2c3d4e5f6a7b8c9d0/upload-url',
        'PUT /casos/a1b2c3d4e5f6a7b8c9d0/a',
        'POST /cases/a1b2c3d4e5f6a7b8c9d0/upload-url',
        'PUT /casos/a1b2c3d4e5f6a7b8c9d0/b',
        'POST /cases/a1b2c3d4e5f6a7b8c9d0/submit',
      ]);
      final body = jsonDecode(server.requests.first.body) as Map;
      expect(body['id_paciente'], 'pac1');
      expect(body['id_solicitud'], isNotEmpty);
      // La carga va sin el token de la app y con los encabezados del backend.
      final put = server.requests[2];
      expect(put.headers.containsKey('Authorization'), isFalse);
      expect(put.headers['Content-Type'], startsWith('image/jpeg'));
    });

    test('exige las dos fotos antes de llamar al backend (RF-02.1)', () async {
      await expectLater(
          cases.submitCase(CaseDraft(patientId: 'pac1', foto1: draft.foto1), data),
          throwsA(isA<AppException>()));
      expect(server.requests, isEmpty);
    });

    test('el detalle trae la predicción y conserva las URL de las fotos', () async {
      await cases.submitCase(draft, data);
      await settle();
      final c = await cases.watchCase('a1b2c3d4e5f6a7b8c9d0').first;
      expect(c!.status, CaseStatus.pendienteValidacion);
      expect(c.prediction!.clasePredicha, LesionClass.melanoma);
      expect(c.foto1.remoteUrl, 'http://almacen/a');
      expect(c.foto1.localPath, isNotNull);
    });
  });

  group('Cola sin conexión (RF-02.4, RNF-08, I18)', () {
    test('sin conexión el caso queda en el dispositivo y se envía al volver', () async {
      connectivity.online = false;
      final queued = await cases.submitCase(draft, data);
      expect(queued.queuedOffline, isTrue);
      expect(queued.id, startsWith('local-'));
      expect(server.requests, isEmpty);
      final mine = await cases.watchMyCases().first;
      expect(mine.first.id, queued.id);

      connectivity.setOnline(true);
      await settle();
      expect(store.queue, isEmpty);
      expect(store.resolvedIds[queued.id], 'a1b2c3d4e5f6a7b8c9d0');
      expect(server.calls.last, 'POST /cases/a1b2c3d4e5f6a7b8c9d0/submit');
      // El id local ahora abre el caso del backend.
      final c = await cases.watchCase(queued.id).first;
      expect(c!.id, 'a1b2c3d4e5f6a7b8c9d0');
    });

    test('un corte de red durante el envío guarda el caso en la cola', () async {
      server.networkDown = true;
      final queued = await cases.submitCase(draft, data);
      expect(queued.queuedOffline, isTrue);
      expect(store.queue.single.requestId, queued.id.substring('local-'.length));
    });

    test('el reenvío usa el mismo id_solicitud para no duplicar el caso', () async {
      connectivity.online = false;
      final queued = await cases.submitCase(draft, data);
      connectivity.setOnline(true);
      await settle();
      final body = jsonDecode(server.requests.first.body) as Map;
      expect('local-${body['id_solicitud']}', queued.id);
    });
  });

  group('Validación (I8)', () {
    test('la clase final solo se manda al corregir', () async {
      final validations = RestValidationRepository(api, hub);
      await validations.registerValidation(
        caseId: 'a1b2c3d4e5f6a7b8c9d0',
        decision: ValidationDecision.confirmar,
        sustentoClinico: ' Lesión simétrica. ',
        claseFinal: LesionClass.noMelanoma,
      );
      final body = jsonDecode(server.requests.last.body) as Map;
      expect(body['decision'], 'confirmar');
      expect(body['sustento_clinico'], 'Lesión simétrica.');
      expect(body.containsKey('clase_final'), isFalse);

      await validations.registerValidation(
        caseId: 'a1b2c3d4e5f6a7b8c9d0',
        decision: ValidationDecision.corregir,
        sustentoClinico: 'Patrón reticular regular.',
        claseFinal: LesionClass.noMelanoma,
      );
      expect((jsonDecode(server.requests.last.body) as Map)['clase_final'], 'no_melanoma');
    });
  });
}
