import 'dart:async';

import 'package:firebase_messaging/firebase_messaging.dart';

import '../../core/errors/app_exception.dart';
import 'api_client.dart';

/// Valor de `tipo` en los datos de la push de casos vencidos
/// (`backend/dermavia/dominio/notificaciones.py`).
const kOverduePushType = 'casos_vencidos';

/// Lo que la app usa de Firebase Cloud Messaging (CONEXION_NUBE.md, N9 y N10).
/// Cada mensaje se entrega como su mapa de datos (`{"tipo": ...}`): la push no
/// trae datos clínicos.
abstract class PushMessaging {
  /// Pide el permiso de notificaciones (Android 13+: `POST_NOTIFICATIONS`).
  Future<bool> requestPermission();
  Future<String?> getToken();
  Stream<String> get onTokenRefresh;
  Future<void> deleteToken();

  /// Push que abrió la app cuando estaba cerrada.
  Future<Map<String, dynamic>?> initialMessage();

  /// Push tocada con la app en segundo plano.
  Stream<Map<String, dynamic>> get onMessageOpenedApp;

  /// Push recibida con la app abierta (Android no la muestra).
  Stream<Map<String, dynamic>> get onMessage;
}

/// [PushMessaging] con el plugin real. Solo en modo `nube`, después de
/// `Firebase.initializeApp`.
///
/// Usa el token de registro de FCM (`getToken`), aunque firebase_messaging 17
/// lo marca obsoleto: su reemplazo (`register`/`onRegistered`) entrega el
/// Firebase Installation ID para el envío directo, y el backend envía con
/// tokens de registro (`firebase_admin.messaging`). Cambiar ambos a la vez.
class PluginPushMessaging implements PushMessaging {
  PluginPushMessaging([FirebaseMessaging? messaging])
      : _messaging = messaging ?? FirebaseMessaging.instance;

  final FirebaseMessaging _messaging;

  @override
  Future<bool> requestPermission() async {
    final settings = await _messaging.requestPermission();
    return settings.authorizationStatus == AuthorizationStatus.authorized ||
        settings.authorizationStatus == AuthorizationStatus.provisional;
  }

  @override
  // ignore: deprecated_member_use
  Future<String?> getToken() => _messaging.getToken();

  @override
  // ignore: deprecated_member_use
  Stream<String> get onTokenRefresh => _messaging.onTokenRefresh;

  @override
  // ignore: deprecated_member_use
  Future<void> deleteToken() => _messaging.deleteToken();

  @override
  Future<Map<String, dynamic>?> initialMessage() async =>
      (await _messaging.getInitialMessage())?.data;

  @override
  Stream<Map<String, dynamic>> get onMessageOpenedApp =>
      FirebaseMessaging.onMessageOpenedApp.map((m) => m.data);

  @override
  Stream<Map<String, dynamic>> get onMessage => FirebaseMessaging.onMessage.map((m) => m.data);
}

/// Registro del dispositivo para las alertas de casos vencidos (I22, N9).
/// Solo los especialistas reciben alertas; el administrador no.
class DeviceRegistration {
  DeviceRegistration(this._api, this._messaging);

  final ApiClient _api;
  final PushMessaging _messaging;
  StreamSubscription<String>? _refreshSub;

  /// El token que quedó de la última vez que se usó la app ya se borró.
  bool _staleTokenCleared = false;
  Future<void>? _clearing;

  /// Al abrir la app. Si el médico anterior la cerró sin cerrar sesión, su token
  /// sigue registrado en el backend: sin esto, el siguiente médico que entre en el
  /// mismo celular registraría ese mismo token y el celular recibiría las alertas
  /// de los dos. La app ya pide el login cada vez que se abre (N5); el token
  /// empieza de cero igual que la sesión.
  Future<void> clearStaleToken() => _clearing ??= _clearStaleToken();

  Future<void> _clearStaleToken() async {
    try {
      await _messaging.deleteToken().timeout(const Duration(seconds: 15));
      _staleTokenCleared = true;
    } on Exception {
      // Sin conexión: se reintenta antes de registrar el dispositivo.
    } finally {
      _clearing = null;
    }
  }

  /// Tras cada login de un especialista: permiso, token y
  /// `POST /users/me/devices`. Si el token cambia, se vuelve a mandar.
  /// Un fallo no impide usar la app: solo no llegarán alertas.
  Future<void> register() async {
    // Primero se descarta el token de la sesión anterior, para no registrarlo
    // también con este médico.
    if (!_staleTokenCleared) await clearStaleToken();
    try {
      if (!await _messaging.requestPermission()) return;
      final token = await _messaging.getToken();
      if (token != null) await _send(token);
      await _refreshSub?.cancel();
      _refreshSub = _messaging.onTokenRefresh.listen((t) => unawaited(_send(t)));
    } on Exception {
      // Sin permiso, sin Google Play Services o sin conexión.
    }
  }

  Future<void> _send(String token) async {
    try {
      await _api.post('/users/me/devices', body: {'token': token});
    } on AppException {
      // Se reintenta en el próximo login o al renovarse el token.
    }
  }

  /// Al cerrar sesión. El backend no tiene un endpoint para quitar el
  /// dispositivo, pero borra los tokens inválidos al enviar la siguiente
  /// alerta: así el celular no recibe las alertas del médico anterior.
  Future<void> unregister() async {
    await _refreshSub?.cancel();
    _refreshSub = null;
    try {
      await _messaging.deleteToken();
    } on Exception {
      // Sin conexión: el token viejo queda en el backend hasta que falle.
    }
  }

  void dispose() => _refreshSub?.cancel();
}
