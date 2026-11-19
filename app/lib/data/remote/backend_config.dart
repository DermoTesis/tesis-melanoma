/// Qué backend usa la app (INTEGRACION_BACKEND.md, I0).
///
/// - `mock`: backend simulado en memoria (pruebas y demo sin red).
/// - `local`: servidor local `python -m dermavia.local` con tokens `dev:<uid>`.
/// - `nube`: Cloud Run + Firebase Authentication (fase 2, pendiente).
enum BackendMode { mock, local, nube }

class BackendConfig {
  const BackendConfig({
    required this.mode,
    required this.apiUrl,
    this.pollInterval = const Duration(seconds: 15),
    this.requestTimeout = const Duration(seconds: 20),
    this.analysisTimeout = const Duration(seconds: 120),
  });

  /// Lee `--dart-define=DERMAVIA_BACKEND=mock|local|nube` y
  /// `--dart-define=DERMAVIA_API_URL=...` (por defecto, el servidor local visto
  /// desde el emulador de Android).
  factory BackendConfig.fromEnvironment() {
    const mode = String.fromEnvironment('DERMAVIA_BACKEND', defaultValue: 'mock');
    const url = String.fromEnvironment('DERMAVIA_API_URL', defaultValue: 'http://10.0.2.2:8080');
    return BackendConfig(
      mode: BackendMode.values.firstWhere((m) => m.name == mode, orElse: () => BackendMode.mock),
      apiUrl: url,
    );
  }

  final BackendMode mode;
  final String apiUrl;

  /// Cada cuánto se refrescan las pantallas abiertas (no hay listeners de
  /// Firestore: las reglas niegan el acceso de clientes).
  final Duration pollInterval;
  final Duration requestTimeout;

  /// `POST /cases/{id}/submit` analiza las fotos dentro de la petición y
  /// puede tardar más en un arranque en frío.
  final Duration analysisTimeout;

  bool get isRemote => mode != BackendMode.mock;
}
