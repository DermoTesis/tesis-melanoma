import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/router/app_router.dart';
import '../core/theme/app_colors.dart';
import '../data/remote/push_messaging.dart';
import '../domain/models/user.dart';
import 'repository_providers.dart';

/// Firebase Cloud Messaging. Se sobrescribe en `main` solo en modo `nube`;
/// con el simulado o el servidor local no hay notificaciones push.
final pushMessagingProvider = Provider<PushMessaging?>((ref) => null);

/// Alertas push de casos vencidos (I22; CONEXION_NUBE.md, N9 y N10). La app
/// lo mantiene vivo desde [DermaviaApp].
final pushNotificationsProvider = Provider<PushNotifications?>((ref) {
  final messaging = ref.watch(pushMessagingProvider);
  if (messaging == null) return null;
  final push = PushNotifications(ref, messaging);
  ref.onDispose(push.dispose);
  return push;
});

class PushNotifications {
  PushNotifications(this._ref, this._messaging)
      : _devices = DeviceRegistration(_ref.read(apiClientProvider), _messaging) {
    // El token que quedó de la última vez no debe pasar al siguiente médico.
    unawaited(_devices.clearStaleToken());
    _ref.listen<AppUser?>(authStateProvider.select((s) => s.value), _onUser, fireImmediately: true);
    _subs.add(_messaging.onMessageOpenedApp.listen(_onOpened));
    _subs.add(_messaging.onMessage.listen(_onForeground));
    unawaited(_messaging.initialMessage().then((data) {
      if (data != null) _onOpened(data);
    }));
  }

  final Ref _ref;
  final PushMessaging _messaging;
  final DeviceRegistration _devices;
  final _subs = <StreamSubscription<Object?>>[];
  String? _registeredUid;

  /// Se tocó una alerta sin sesión abierta (la app pide el login cada vez que
  /// se abre, N5): `/alertas` se abre después del login.
  bool _openAlertsAfterLogin = false;

  static bool _isOverdue(Map<String, dynamic> data) => data['tipo'] == kOverduePushType;

  AppUser? get _user => _ref.read(authRepositoryProvider).currentUser;

  void _onUser(AppUser? previous, AppUser? user) {
    if (user != null && user.isSpecialist) {
      if (_registeredUid != user.uid) {
        _registeredUid = user.uid;
        unawaited(_devices.register());
      }
      if (_openAlertsAfterLogin) {
        _openAlertsAfterLogin = false;
        _openAlerts();
      }
    } else if (user == null && _registeredUid != null) {
      _registeredUid = null;
      unawaited(_devices.unregister());
    }
  }

  void _onOpened(Map<String, dynamic> data) {
    if (!_isOverdue(data)) return;
    if (_user?.isSpecialist ?? false) {
      _openAlerts();
    } else {
      _openAlertsAfterLogin = true;
    }
  }

  /// Con la app abierta Android no muestra la notificación: se refrescan las
  /// pantallas y se avisa dentro de la app.
  void _onForeground(Map<String, dynamic> data) {
    if (!_isOverdue(data) || !(_user?.isSpecialist ?? false)) return;
    _ref.read(refreshHubProvider).notify();
    final context = rootNavigatorKey.currentContext;
    if (context == null) return;
    ScaffoldMessenger.maybeOf(context)
      ?..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
        content: const Text('Tienes casos pendientes de validación que superaron el tiempo límite.'),
        backgroundColor: AppColors.ink,
        action: SnackBarAction(label: 'Ver', onPressed: _openAlerts),
      ));
  }

  void _openAlerts() {
    // Después del cuadro actual: el redirect del login se aplica primero.
    WidgetsBinding.instance.addPostFrameCallback((_) => _ref.read(routerProvider).go('/alertas'));
    WidgetsBinding.instance.scheduleFrame();
  }

  void dispose() {
    for (final s in _subs) {
      unawaited(s.cancel());
    }
    _devices.dispose();
  }
}
