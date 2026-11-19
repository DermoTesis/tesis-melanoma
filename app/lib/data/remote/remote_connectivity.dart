import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';

import '../../domain/repositories/repositories.dart';

/// Conectividad real (I21). La app está "en línea" si el dispositivo tiene
/// red, el servidor respondió la última petición y no se está simulando la
/// falta de conexión desde el perfil.
class RemoteConnectivityService implements ConnectivityService {
  RemoteConnectivityService({Stream<bool>? deviceChanges, bool initialDeviceOnline = true})
      : _device = initialDeviceOnline {
    _sub = (deviceChanges ?? _fromPlugin()).listen((online) {
      _device = online;
      _emit();
    });
  }

  static Stream<bool> _fromPlugin() async* {
    final connectivity = Connectivity();
    bool hasNetwork(List<ConnectivityResult> r) => r.any((x) => x != ConnectivityResult.none);
    try {
      yield hasNetwork(await connectivity.checkConnectivity());
      yield* connectivity.onConnectivityChanged.map(hasNetwork);
    } catch (_) {
      // Sin el plugin (p. ej. en pruebas) se asume que hay red.
      yield true;
    }
  }

  late final StreamSubscription<bool> _sub;
  final _changes = StreamController<bool>.broadcast();
  bool _device;
  bool _reachable = true;
  bool _simulatedOffline = false;
  bool _last = true;

  @override
  bool get isOnline => _device && _reachable && !_simulatedOffline;

  @override
  Stream<bool> onlineChanges() async* {
    yield isOnline;
    yield* _changes.stream;
  }

  /// Interruptor "Simular sin conexión" del perfil.
  @override
  void setOnline(bool online) {
    _simulatedOffline = !online;
    _emit();
  }

  /// Lo llama `ApiClient` tras cada petición.
  void reportReachability(bool reachable) {
    if (_reachable == reachable) return;
    _reachable = reachable;
    _emit();
  }

  void _emit() {
    final now = isOnline;
    if (now == _last) return;
    _last = now;
    if (!_changes.isClosed) _changes.add(now);
  }

  void dispose() {
    _sub.cancel();
    _changes.close();
  }
}
