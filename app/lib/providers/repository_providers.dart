import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/mock/mock_backend.dart';
import '../data/mock/mock_repositories.dart';
import '../data/remote/api_client.dart';
import '../data/remote/backend_config.dart';
import '../data/remote/codecs.dart';
import '../data/remote/local_case_store.dart';
import '../data/remote/refresh_hub.dart';
import '../data/remote/remote_connectivity.dart';
import '../data/remote/rest_repositories.dart';
import '../data/remote/token_provider.dart';
import '../domain/models/audit_event.dart';
import '../domain/models/clinical_case.dart';
import '../domain/models/patient.dart';
import '../domain/models/report.dart';
import '../domain/models/user.dart';
import '../domain/models/validation.dart';
import '../domain/repositories/repositories.dart';

// Único punto de cambio entre el backend simulado y el real. Se elige con
// `--dart-define=DERMAVIA_BACKEND=mock|local|nube` (INTEGRACION_BACKEND.md, I0);
// por defecto, el simulado, que usan las pruebas.

final backendConfigProvider = Provider<BackendConfig>((ref) => BackendConfig.fromEnvironment());

bool _isRemote(Ref ref) => ref.watch(backendConfigProvider).isRemote;

// --- Backend simulado ---

final mockBackendProvider = Provider<MockBackend>((ref) {
  final backend = MockBackend();
  ref.onDispose(backend.dispose);
  return backend;
});

// --- Backend real (servidor local o Cloud Run) ---

/// Datos guardados en el dispositivo (cola offline, fotos, orden manual).
/// Se cargan en `main` antes de arrancar la app.
final localCaseStoreProvider = Provider<LocalCaseStore>((ref) => LocalCaseStore());

final refreshHubProvider = Provider<RefreshHub>((ref) {
  final hub = RefreshHub(pollInterval: ref.watch(backendConfigProvider).pollInterval);
  ref.onDispose(hub.dispose);
  return hub;
});

final remoteConnectivityProvider = Provider<RemoteConnectivityService>((ref) {
  final service = RemoteConnectivityService();
  ref.onDispose(service.dispose);
  return service;
});

final tokenProviderProvider = Provider<TokenProvider>((ref) {
  final config = ref.watch(backendConfigProvider);
  switch (config.mode) {
    case BackendMode.local:
      // Las cuentas que el admin crea durante la sesión del servidor local no
      // están en DevAccounts: su uid se busca con la cuenta de administrador.
      final asAdmin = ApiClient(
        baseUrl: config.apiUrl,
        token: () async => 'dev:${DevAccounts.adminUid}',
        timeout: config.requestTimeout,
      );
      ref.onDispose(asAdmin.close);
      return DevTokenProvider(resolveUid: (correo) async {
        try {
          final users = await asAdmin.get('/admin/users') as List;
          return users.cast<Json>().where((u) => u['correo'] == correo).firstOrNull?['uid']
              as String?;
        } on Exception {
          return null;
        }
      });
    case BackendMode.nube:
      // Firebase ya está inicializado en `main` (CONEXION_NUBE.md, N2).
      return FirebaseTokenProvider(PluginFirebaseAuthGateway());
    case BackendMode.mock:
      // El simulado no usa tokens: sus repositorios llevan la sesión.
      return DevTokenProvider();
  }
});

/// Correo de Firebase para definir la contraseña (activación y recuperación,
/// I15 e I16). Null con el servidor local, que no envía correos.
final passwordLinkSenderProvider = Provider<PasswordLinkSender?>((ref) {
  final tokens = ref.watch(tokenProviderProvider);
  return tokens is PasswordLinkSender ? tokens as PasswordLinkSender : null;
});

final Provider<ApiClient> apiClientProvider = Provider<ApiClient>((ref) {
  final config = ref.watch(backendConfigProvider);
  final tokens = ref.watch(tokenProviderProvider);
  final connectivity = ref.watch(remoteConnectivityProvider);
  final client = ApiClient(
    baseUrl: config.apiUrl,
    token: tokens.token,
    timeout: config.requestTimeout,
    onReachability: connectivity.reportReachability,
    onUnauthenticated: () {
      final auth = ref.read(authRepositoryProvider);
      if (auth is RestAuthRepository) auth.onUnauthenticated();
    },
  );
  ref.onDispose(client.close);
  return client;
});

// --- Repositorios ---

final Provider<AuthRepository> authRepositoryProvider = Provider<AuthRepository>((ref) {
  if (!_isRemote(ref)) return MockAuthRepository(ref.watch(mockBackendProvider));
  final repo = RestAuthRepository(ref.watch(apiClientProvider), ref.watch(tokenProviderProvider));
  ref.onDispose(repo.dispose);
  return repo;
});

final adminRepositoryProvider = Provider<AdminRepository>((ref) => _isRemote(ref)
    ? RestAdminRepository(ref.watch(apiClientProvider), ref.watch(refreshHubProvider),
        links: ref.watch(passwordLinkSenderProvider))
    : MockAdminRepository(ref.watch(mockBackendProvider)));

final patientRepositoryProvider = Provider<PatientRepository>((ref) => _isRemote(ref)
    ? RestPatientRepository(ref.watch(apiClientProvider), ref.watch(refreshHubProvider))
    : MockPatientRepository(ref.watch(mockBackendProvider)));

final caseRepositoryProvider = Provider<CaseRepository>((ref) {
  if (!_isRemote(ref)) return MockCaseRepository(ref.watch(mockBackendProvider));
  final repo = RestCaseRepository(
    ref.watch(apiClientProvider),
    ref.watch(refreshHubProvider),
    ref.watch(localCaseStoreProvider),
    ref.watch(connectivityServiceProvider),
    // La cola offline solo muestra y envía los casos del médico con sesión (N5).
    currentUid: () => ref.read(authRepositoryProvider).currentUser?.uid,
    analysisTimeout: ref.watch(backendConfigProvider).analysisTimeout,
  );
  ref.onDispose(repo.dispose);
  return repo;
});

final validationRepositoryProvider = Provider<ValidationRepository>((ref) => _isRemote(ref)
    ? RestValidationRepository(ref.watch(apiClientProvider), ref.watch(refreshHubProvider))
    : MockValidationRepository(ref.watch(mockBackendProvider)));

final reportRepositoryProvider = Provider<ReportRepository>((ref) => _isRemote(ref)
    ? RestReportRepository(ref.watch(apiClientProvider), ref.watch(refreshHubProvider),
        ref.watch(localCaseStoreProvider))
    : MockReportRepository(ref.watch(mockBackendProvider)));

final auditRepositoryProvider = Provider<AuditRepository>((ref) => _isRemote(ref)
    ? RestAuditRepository(ref.watch(apiClientProvider), ref.watch(refreshHubProvider))
    : MockAuditRepository(ref.watch(mockBackendProvider)));

final connectivityServiceProvider = Provider<ConnectivityService>((ref) => _isRemote(ref)
    ? ref.watch(remoteConnectivityProvider)
    : MockConnectivityService(ref.watch(mockBackendProvider)));

/// Reloj de la aplicación (inyectable para pruebas). Con el backend real es
/// el reloj del dispositivo.
final clockProvider = Provider<DateTime Function()>(
    (ref) => _isRemote(ref) ? DateTime.now : ref.watch(mockBackendProvider).now);

// --- Flujos de lectura ---

final authStateProvider = StreamProvider<AppUser?>(
    (ref) => ref.watch(authRepositoryProvider).authStateChanges());

final onlineProvider = StreamProvider<bool>(
    (ref) => ref.watch(connectivityServiceProvider).onlineChanges());

// Los datos son de la sesión: al cambiar de usuario no puede quedar nada leído con
// la cuenta anterior (los casos son privados de cada médico). Por eso cada flujo:
// - observa el uid de la sesión y, sin sesión, se vacía de inmediato;
// - es autoDispose: al cerrar sesión la app vuelve a /login, se cierran todas las
//   pantallas y su estado se destruye. Riverpod conserva el valor anterior mientras
//   recarga, así que la siguiente cuenta empieza desde cero en vez de ver, por unos
//   segundos, lo que vio la anterior.

/// Uid de la sesión actual; null sin sesión.
String? _sessionUid(Ref ref) => ref.watch(authStateProvider.select((s) => s.value?.uid));

/// Flujo de datos de la sesión: [empty] sin sesión, [read] con ella.
Stream<T> _forSession<T>(Ref ref, T empty, Stream<T> Function() read) =>
    _sessionUid(ref) == null ? Stream.value(empty) : read();

final myCasesProvider = StreamProvider.autoDispose<List<ClinicalCase>>((ref) =>
    _forSession(ref, const [], () => ref.watch(caseRepositoryProvider).watchMyCases()));

final caseProvider = StreamProvider.autoDispose.family<ClinicalCase?, String>((ref, id) =>
    _forSession(ref, null, () => ref.watch(caseRepositoryProvider).watchCase(id)));

final patientCasesProvider = StreamProvider.autoDispose.family<List<ClinicalCase>, String>(
    (ref, patientId) => _forSession(ref, const [],
        () => ref.watch(caseRepositoryProvider).watchCasesForPatient(patientId)));

final patientsProvider = StreamProvider.autoDispose<List<Patient>>((ref) =>
    _forSession(ref, const [], () => ref.watch(patientRepositoryProvider).watchPatients()));

final patientProvider = StreamProvider.autoDispose.family<Patient?, String>((ref, id) =>
    _forSession(ref, null, () => ref.watch(patientRepositoryProvider).watchPatient(id)));

final validationsProvider =
    StreamProvider.autoDispose.family<List<ClinicalValidation>, String>((ref, caseId) =>
        _forSession(ref, const [],
            () => ref.watch(validationRepositoryProvider).watchValidations(caseId)));

final reportProvider = StreamProvider.autoDispose.family<CaseReport?, String>((ref, caseId) =>
    _forSession(ref, null, () => ref.watch(reportRepositoryProvider).watchReport(caseId)));

final usersProvider = StreamProvider.autoDispose<List<AppUser>>((ref) =>
    _forSession(ref, const [], () => ref.watch(adminRepositoryProvider).watchUsers()));

final auditEventsProvider = StreamProvider.autoDispose<List<AuditEvent>>((ref) =>
    _forSession(ref, const [], () => ref.watch(auditRepositoryProvider).watchEvents()));
