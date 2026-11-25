import 'dart:async';

/// Convierte lecturas REST en `Stream`s equivalentes a los listeners de
/// Firestore (I0): la app no puede leer Firestore (las reglas lo niegan), así
/// que cada `watch` pide los datos al suscribirse, los vuelve a pedir cada
/// [pollInterval] mientras haya alguien escuchando y de inmediato después de
/// cada escritura ([notify]).
class RefreshHub {
  RefreshHub({this.pollInterval = const Duration(seconds: 15)});

  final Duration? pollInterval;
  final _changes = StreamController<void>.broadcast();

  /// Avisa a todos los `watch` activos que vuelvan a leer.
  void notify() {
    if (!_changes.isClosed) _changes.add(null);
  }

  /// Si una lectura falla después de haber emitido un valor, se conserva el
  /// último valor (p. ej. sin conexión) en vez de mostrar un error.
  Stream<T> watch<T>(Future<T> Function() fetch) {
    late StreamController<T> controller;
    StreamSubscription<void>? sub;
    Timer? timer;
    var hasValue = false;
    var loading = false;
    var again = false;

    Future<void> load() async {
      if (controller.isClosed) return;
      if (loading) {
        again = true;
        return;
      }
      loading = true;
      try {
        final value = await fetch();
        if (!controller.isClosed) {
          controller.add(value);
          hasValue = true;
        }
      } catch (error, stack) {
        if (!hasValue && !controller.isClosed) controller.addError(error, stack);
      } finally {
        loading = false;
        if (again) {
          again = false;
          unawaited(load());
        }
      }
    }

    controller = StreamController<T>(
      onListen: () {
        unawaited(load());
        sub = _changes.stream.listen((_) => load());
        final every = pollInterval;
        if (every != null) timer = Timer.periodic(every, (_) => load());
      },
      onCancel: () {
        timer?.cancel();
        return sub?.cancel();
      },
    );
    return controller.stream;
  }

  void dispose() => _changes.close();
}
