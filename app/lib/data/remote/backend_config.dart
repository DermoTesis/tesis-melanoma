/// Qué backend usa la app (INTEGRACION_BACKEND.md, I0; CONEXION_NUBE.md).
///
/// - `mock`: backend simulado en memoria (pruebas y demo sin red).
/// - `local`: servidor local `python -m dermavia.local` con tokens `dev:<uid>`.
/// - `nube`: API en Cloud Run + Firebase Authentication y Cloud Messaging.
enum BackendMode { mock, local, nube }

class BackendConfig {
  const BackendConfig({
    required this.mode,
    required this.apiUrl,
    this.pollInterval = const Duration(seconds: 15),
    this.requestTimeout = const Duration(seconds: 20),
    this.analysisTimeout = const Duration(seconds: 120),
  });

  /// Servidor local visto desde el emulador de Android.
  static const localApiUrl = 'http://10.0.2.2:8080';

  /// API desplegada en Cloud Run (proyecto `tesis-dermavia`).
  static const cloudApiUrl = 'https://dermavia-api-432424057783.southamerica-west1.run.app';

  /// Cloud Run no tiene instancias mínimas (CONEXION_NUBE.md, C4): la primera
  /// petición tras un rato sin uso espera el arranque del contenedor y la
  /// carga del modelo. Ajustar cuando EXP-05 mida el arranque en frío.
  static const cloudRequestTimeout = Duration(seconds: 45);

  /// Lee `--dart-define=DERMAVIA_BACKEND=mock|local|nube` y, opcionalmente,
  /// `--dart-define=DERMAVIA_API_URL=...`. Sin URL, `local` usa el servidor
  /// local y `nube` la API de Cloud Run.
  factory BackendConfig.fromEnvironment() {
    const mode = String.fromEnvironment('DERMAVIA_BACKEND', defaultValue: 'mock');
    const url = String.fromEnvironment('DERMAVIA_API_URL');
    return BackendConfig.forMode(
      BackendMode.values.firstWhere((m) => m.name == mode, orElse: () => BackendMode.mock),
      apiUrl: url.isEmpty ? null : url,
    );
  }

  factory BackendConfig.forMode(BackendMode mode, {String? apiUrl}) {
    final cloud = mode == BackendMode.nube;
    return BackendConfig(
      mode: mode,
      apiUrl: apiUrl ?? (cloud ? cloudApiUrl : localApiUrl),
      requestTimeout: cloud ? cloudRequestTimeout : const Duration(seconds: 20),
    );
  }

  final BackendMode mode;
  final String apiUrl;

  /// Cada cuánto se refrescan las pantallas abiertas (no hay listeners de
  /// Firestore: las reglas niegan el acceso de clientes).
  final Duration pollInterval;
  final Duration requestTimeout;

  /// `POST /cases/{id}/submit` analiza las fotos dentro de la petición y
  /// puede tardar más en un arranque en frío (Cloud Run corta a los 300 s).
  final Duration analysisTimeout;

  bool get isRemote => mode != BackendMode.mock;

  /// Firebase (Authentication y Cloud Messaging) solo se usa con la nube.
  bool get usesFirebase => mode == BackendMode.nube;
}
