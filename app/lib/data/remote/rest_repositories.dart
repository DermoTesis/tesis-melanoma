// Implementación de los contratos de lib/domain/repositories con la API REST
// del backend (INTEGRACION_BACKEND.md). Las reglas de negocio las aplica el
// backend; aquí solo se traduce HTTP y se mantienen los datos locales (cola
// offline, fotos capturadas en el dispositivo y orden manual del panel).

import 'dart:async';
import 'dart:io';

import 'package:uuid/uuid.dart';

import '../../core/errors/app_exception.dart';
import '../../domain/models/audit_event.dart';
import '../../domain/models/clinical_case.dart';
import '../../domain/models/patient.dart';
import '../../domain/models/prediction.dart';
import '../../domain/models/report.dart';
import '../../domain/models/user.dart';
import '../../domain/models/validation.dart';
import '../../domain/repositories/repositories.dart';
import 'api_client.dart';
import 'codecs.dart';
import 'local_case_store.dart';
import 'refresh_hub.dart';
import 'token_provider.dart';

/// Mensaje para los flujos de cuenta que usan el correo de Firebase (I15,
/// I16) cuando la app habla con el servidor local, que no envía correos.
const kFirebasePending =
    'Esta función usa el correo de Firebase y no está disponible con el '
    'servidor local. Pide al administrador que active tu cuenta.';

/// El backend creó la cuenta, pero Firebase no pudo enviar el correo de
/// activación (CONEXION_NUBE.md, N7). El administrador puede reenviarlo.
class ActivationEmailException extends AppException {
  const ActivationEmailException(this.user)
      : super('Cuenta creada, pero no se pudo enviar el correo de activación.',
            code: 'activation-email-failed');

  final AppUser user;
}

List<Json> _list(dynamic json) => [for (final e in json as List) e as Json];

/// Firebase Authentication (nube) o tokens de desarrollo (servidor local) +
/// módulo Identidad (I13–I16).
class RestAuthRepository implements AuthRepository {
  RestAuthRepository(this._api, this._tokens);

  final ApiClient _api;
  final TokenProvider _tokens;
  final _changes = StreamController<AppUser?>.broadcast();
  AppUser? _user;

  void _set(AppUser? user) {
    _user = user;
    if (!_changes.isClosed) _changes.add(user);
  }

  @override
  Stream<AppUser?> authStateChanges() async* {
    yield _user;
    yield* _changes.stream;
  }

  @override
  AppUser? get currentUser => _user;

  @override
  Future<AppUser> signIn(String correo, String password) async {
    await _tokens.signIn(correo, password);
    final AppUser user;
    try {
      // La primera petición autenticada activa la cuenta pendiente.
      user = userFromJson(await _api.get('/users/me') as Json);
    } on AppException catch (e) {
      await _tokens.signOut();
      // Cuenta sin perfil en Dermavía: mismo error genérico (HU04·CA2).
      if (e.code == 'permission-denied' || e.code == 'unauthenticated') {
        throw const AuthException();
      }
      rethrow;
    }
    // El backend responde /users/me aunque el acceso clínico esté revocado
    // (solo lo bloquea en las rutas clínicas): la app no deja entrar (I14).
    if (user.isSpecialist && !user.clinicalAccess) {
      await _tokens.signOut();
      throw const PermissionDeniedException(
          'Tu acceso clínico fue revocado. Comunícate con el administrador del sistema.');
    }
    _set(user);
    return user;
  }

  @override
  Future<void> signOut() async {
    await _tokens.signOut();
    _set(null);
  }

  /// El backend respondió 401: la sesión ya no es válida.
  void onUnauthenticated() {
    if (_user != null) unawaited(signOut());
  }

  @override
  Future<AppUser> acceptScope() async {
    final user = userFromJson(await _api.post('/users/me/terms') as Json);
    _set(user);
    return user;
  }

  // Flujos de cuenta con enlace por correo. En la nube los dos usan
  // sendPasswordResetEmail de Firebase: la contraseña se define en la página
  // de Firebase y la primera petición autenticada activa la cuenta pendiente.
  // La activación dentro de la app (`/activar/:uid`) es solo del simulado.

  @override
  Future<ActivationTicket?> findActivation(String correo) async =>
      throw const AppException(kFirebasePending, code: 'unimplemented');

  @override
  Future<ActivationTicket?> getActivation(String uid) async => null;

  @override
  Future<AppUser> activateAccount(String uid, String password) async =>
      throw const AppException(kFirebasePending, code: 'unimplemented');

  @override
  Future<PasswordResetTicket> requestPasswordReset(String correo) async {
    final tokens = _tokens;
    if (tokens is! PasswordLinkSender) {
      throw const AppException(kFirebasePending, code: 'unimplemented');
    }
    if (correo.trim().isEmpty) throw const AppException('Ingresa tu correo institucional.');
    await (tokens as PasswordLinkSender).sendPasswordLink(correo);
    // Firebase lleva el vencimiento del enlace (1 h); la app no lo controla.
    return PasswordResetTicket(correo: correo.trim());
  }

  @override
  Future<void> resetPassword(String correo, String newPassword) async =>
      throw const AppException(kFirebasePending, code: 'unimplemented');

  @override
  Future<PasswordResetTicket?> expireResetLink(String correo) async => null;

  void dispose() => _changes.close();
}

/// Módulo Identidad, funciones del administrador.
class RestAdminRepository implements AdminRepository {
  RestAdminRepository(this._api, this._hub, {PasswordLinkSender? links}) : _links = links;

  final ApiClient _api;
  final RefreshHub _hub;

  /// Firebase en la nube; null con el servidor local, que no envía correos.
  final PasswordLinkSender? _links;

  @override
  Stream<List<AppUser>> watchUsers() => _hub.watch(() async {
        final users = _list(await _api.get('/admin/users')).map(userFromJson);
        return users.where((u) => u.isSpecialist).toList()
          ..sort((a, b) => a.nombres.compareTo(b.nombres));
      });

  @override
  Future<AppUser> createSpecialist({
    required String nombres,
    required String correo,
    required String dni,
    required String cmp,
    required bool colegiaturaVerificada,
  }) async {
    final json = await _api.post('/admin/specialists', body: {
      'nombres': nombres.trim(),
      'correo': correo.trim(),
      'dni': dni.trim(),
      'numero_colegiatura': cmp.replaceAll(' ', ''),
      'colegiatura_verificada': colegiaturaVerificada,
    });
    _hub.notify();
    final user = userFromJson(json as Json);
    // El backend no envía correos: la app pide a Firebase el enlace para
    // definir la contraseña. No cambia la sesión del administrador (I15).
    final links = _links;
    if (links != null) {
      try {
        await links.sendPasswordLink(user.correo);
      } on AppException {
        throw ActivationEmailException(user);
      }
    }
    return user;
  }

  @override
  Future<void> resendActivationLink(String correo) async {
    final links = _links;
    if (links == null) throw const AppException(kFirebasePending, code: 'unimplemented');
    await links.sendPasswordLink(correo);
  }

  @override
  Future<void> setClinicalAccess(String uid, bool enabled) async {
    await _api.patch('/admin/users/$uid/role', body: {'acceso_clinico': enabled});
    _hub.notify();
  }
}

/// Módulo Auditoría (bitácora del administrador).
class RestAuditRepository implements AuditRepository {
  RestAuditRepository(this._api, this._hub);

  final ApiClient _api;
  final RefreshHub _hub;

  @override
  Stream<List<AuditEvent>> watchEvents() => _hub.watch(() async => [
        for (final j in _list(await _api.get('/admin/audit', query: {'limite': '200'})))
          ?auditEventFromJson(j),
      ]);
}

/// Módulo Pacientes.
class RestPatientRepository implements PatientRepository {
  RestPatientRepository(this._api, this._hub);

  final ApiClient _api;
  final RefreshHub _hub;

  @override
  Stream<List<Patient>> watchPatients() =>
      _hub.watch(() async => _list(await _api.get('/patients')).map(patientFromJson).toList());

  @override
  Stream<Patient?> watchPatient(String id) => _hub.watch(() async {
        try {
          return patientFromJson(await _api.get('/patients/$id') as Json);
        } on AppException catch (e) {
          if (e.code == 'not-found') return null;
          rethrow;
        }
      });

  @override
  Future<Patient?> findByHistoriaClinica(String hc) async {
    final found = _list(await _api.get('/patients', query: {'hc': Patient.normalizeHc(hc)}));
    return found.isEmpty ? null : patientFromJson(found.first);
  }

  @override
  Future<Patient> registerPatient({
    required String numeroHistoriaClinica,
    required String nombres,
    required DateTime fechaNacimiento,
    required Sex sexo,
    required Phototype fototipo,
  }) async {
    final json = await _api.post('/patients',
        body: patientToJson(
          numeroHistoriaClinica: Patient.normalizeHc(numeroHistoriaClinica),
          nombres: nombres.trim(),
          fechaNacimiento: fechaNacimiento,
          sexo: sexo,
          fototipo: fototipo,
        ));
    _hub.notify();
    return patientFromJson(json as Json);
  }

  @override
  Future<Patient> registerConsent(String patientId) async {
    final json = await _api.post('/patients/$patientId/consent');
    _hub.notify();
    return patientFromJson(json as Json);
  }

  @override
  Future<Patient> revokeConsent(String patientId) async {
    final json = await _api.delete('/patients/$patientId/consent');
    _hub.notify();
    return patientFromJson(json as Json);
  }
}

/// Módulo Gestión de Casos (I4, I5, I17–I20).
class RestCaseRepository implements CaseRepository {
  RestCaseRepository(
    this._api,
    this._hub,
    this._store,
    this._connectivity, {
    required String? Function() currentUid,
    this.analysisTimeout = const Duration(seconds: 120),
    Uuid uuid = const Uuid(),
  })  : _currentUid = currentUid,
        _uuid = uuid {
    _connectivitySub = _connectivity.onlineChanges().listen((online) {
      if (online) unawaited(flushOfflineQueue());
    });
  }

  final ApiClient _api;
  final RefreshHub _hub;
  final LocalCaseStore _store;
  final ConnectivityService _connectivity;

  /// Uid del médico con sesión: la cola offline solo muestra y envía sus
  /// casos (CONEXION_NUBE.md, N5).
  final String? Function() _currentUid;
  final Duration analysisTimeout;
  final Uuid _uuid;
  late final StreamSubscription<bool> _connectivitySub;
  bool _flushing = false;

  /// URL firmadas del detalle, reutilizadas mientras no venzan, para que el
  /// refresco periódico no vuelva a descargar las fotos (vencen en 15 min).
  final _urls = <String, (DateTime, CaseImage, CaseImage)>{};
  static const _urlReuse = Duration(minutes: 10);

  /// Casos cuya foto de la lista ya se intentó recuperar mientras la app está abierta.
  final _photoAttempts = <String>{};

  // Último valor leído, para mostrar algo sin conexión, y de quién es.
  List<ClinicalCase> _lastMine = const [];
  String? _lastMineUid;

  ClinicalCase _decode(Json json) =>
      caseFromJson(json, localPaths: _store.localImages[json['id']] ?? const {});

  ClinicalCase _withStableUrls(ClinicalCase c) {
    final cached = _urls[c.id];
    final now = DateTime.now();
    if (cached != null && now.difference(cached.$1) < _urlReuse) {
      return c.copyWith(
        foto1: c.foto1.copyWith(remoteUrl: cached.$2.remoteUrl),
        foto2: c.foto2.copyWith(remoteUrl: cached.$3.remoteUrl),
      );
    }
    if (c.foto1.remoteUrl != null || c.foto2.remoteUrl != null) {
      _urls[c.id] = (now, c.foto1, c.foto2);
    }
    return c;
  }

  /// Las listas del backend no traen las URL de las fotos; solo el detalle del caso.
  /// Las miniaturas salen de la copia local, que solo existe si el caso se registró en
  /// este dispositivo y la app no se reinstaló. Para los demás casos se pide el detalle
  /// una vez y se guarda la foto de la miniatura (foto 2): desde entonces las listas la
  /// muestran, también sin conexión.
  List<ClinicalCase> _restoreListPhotos(List<ClinicalCase> cases) {
    final missing = <String>[];
    for (final c in cases) {
      // En REGISTRADO las fotos pueden no haberse subido todavía.
      if (c.id.startsWith('local-') || c.status == CaseStatus.registrado) continue;
      final path = c.foto2.localPath;
      if (path != null && File(path).existsSync()) continue;
      if (_photoAttempts.add(c.id)) missing.add(c.id);
    }
    if (missing.isNotEmpty) unawaited(_downloadListPhotos(missing));
    return cases;
  }

  Future<void> _downloadListPhotos(List<String> ids) async {
    var saved = false;
    for (var i = 0; i < ids.length; i++) {
      final id = ids[i];
      try {
        final url = caseFromJson(await _api.get('/cases/$id') as Json).foto2.remoteUrl;
        if (url == null) continue;
        await _store.savePhoto(id, ImageView.foto2, await _api.download(url));
        saved = true;
      } on NetworkException {
        // Sin conexión: se reintentan cuando las listas se vuelvan a leer.
        _photoAttempts.removeAll(ids.sublist(i));
        break;
      } on AppException {
        // Sin foto o caso ajeno (cambió la sesión): queda la imagen de relleno.
      }
    }
    if (saved) _hub.notify();
  }

  /// Casos de la cola del médico con sesión. Los de otro médico esperan a
  /// que su dueño vuelva a entrar.
  List<QueuedCase> _myQueue() {
    final uid = _currentUid();
    return [for (final q in _store.queue) if (q.belongsTo(uid)) q];
  }

  List<ClinicalCase> _queued({String? patientId}) => [
        for (final q in _myQueue())
          if (patientId == null || q.patientId == patientId) q.toCase(),
      ];

  @override
  Stream<List<ClinicalCase>> watchMyCases() => _hub.watch(() async {
        if (_myQueue().isNotEmpty && _connectivity.isOnline) unawaited(flushOfflineQueue());
        final uid = _currentUid();
        if (_lastMineUid != uid) {
          // Otro médico: los casos leídos antes no son suyos.
          _lastMine = const [];
          _lastMineUid = uid;
        }
        try {
          _lastMine = _restoreListPhotos(_list(await _api.get('/cases')).map(_decode).toList());
        } on NetworkException {
          // Sin conexión: se muestran los últimos casos leídos y la cola.
        }
        return [..._queued(), ..._lastMine];
      });

  @override
  Stream<ClinicalCase?> watchCase(String id) => _hub.watch(() async {
        var remoteId = id;
        if (id.startsWith('local-')) {
          final resolved = _store.resolvedIds[id];
          if (resolved == null) {
            return _myQueue().where((q) => q.localId == id).firstOrNull?.toCase();
          }
          remoteId = resolved;
        }
        try {
          return _withStableUrls(_decode(await _api.get('/cases/$remoteId') as Json));
        } on AppException catch (e) {
          if (e.code == 'not-found') return null;
          rethrow;
        }
      });

  @override
  Stream<List<ClinicalCase>> watchCasesForPatient(String patientId) => _hub.watch(() async => [
        ..._queued(patientId: patientId),
        ..._restoreListPhotos(
            _list(await _api.get('/patients/$patientId/cases')).map(_decode).toList()),
      ]);

  @override
  Future<ClinicalCase> submitCase(CaseDraft draft, ClinicalData data) async {
    final pan = draft.foto1?.localPath;
    final close = draft.foto2?.localPath;
    if (pan == null || close == null) {
      throw const AppException('El caso requiere dos fotos aptas de la lesión.');
    }
    if (data.ubicacionLesion.trim().isEmpty) {
      throw const AppException('Indica la ubicación corporal de la lesión.');
    }
    final owner = _currentUid();
    if (owner == null) {
      throw const AppException('Tu sesión expiró. Inicia sesión otra vez.', code: 'unauthenticated');
    }
    final requestId = _uuid.v4();
    final paths = await _store.keepPhotos(
        requestId, {ImageView.foto1: pan, ImageView.foto2: close});
    final queued = QueuedCase(
      requestId: requestId,
      ownerUid: owner,
      patientId: draft.patientId,
      clinicalData: data,
      createdAt: DateTime.now(),
      imagePaths: paths,
    );
    if (!_connectivity.isOnline) return _enqueue(queued);
    try {
      final c = await _register(queued);
      unawaited(_analyze(c.id));
      return c;
    } on NetworkException {
      return _enqueue(queued);
    }
  }

  Future<ClinicalCase> _enqueue(QueuedCase q) async {
    await _store.enqueue(q);
    _hub.notify();
    return q.toCase();
  }

  /// `POST /cases` (idempotente con `id_solicitud`) y carga de las dos fotos
  /// a sus URL firmadas (I17, I19). No espera el análisis.
  Future<ClinicalCase> _register(QueuedCase q) async {
    final json = await _api.post('/cases', body: {
      'id_paciente': q.patientId,
      'datos_clinicos': clinicalDataToJson(q.clinicalData),
      'id_solicitud': q.requestId,
    }) as Json;
    final c = caseFromJson(json, localPaths: q.imagePaths);
    await _store.setLocalImages(c.id, q.imagePaths);
    if (c.status == CaseStatus.registrado || c.status == CaseStatus.errorAnalisis) {
      for (final view in ImageView.values) {
        await _uploadPhoto(c.id, view, q.imagePaths[view]!);
      }
    }
    return c;
  }

  Future<void> _uploadPhoto(String caseId, ImageView view, String path) async {
    final file = File(path);
    if (!await file.exists()) {
      throw const AppException('No se encontró una de las fotos del caso. Vuelve a capturarla.');
    }
    final bytes = await file.readAsBytes();
    if (bytes.length > 20 * 1024 * 1024) {
      throw const AppException('Una de las fotos supera los 20 MB.');
    }
    // La URL vence en 15 min: se pide justo antes de subir.
    final target = await _api.post('/cases/$caseId/upload-url', body: {
      'vista': imageViewCodes[view],
      'tipo_contenido': path.toLowerCase().endsWith('.png') ? 'image/png' : 'image/jpeg',
    }) as Json;
    await _api.upload(
      target['url'] as String,
      bytes,
      method: target['metodo'] as String? ?? 'PUT',
      headers: (target['encabezados'] as Map).cast<String, String>(),
    );
  }

  /// `POST /cases/{id}/submit` analiza dentro de la petición: corre en segundo
  /// plano y, al terminar, refresca las pantallas. Si falla, el backend deja el
  /// caso en ERROR_ANALISIS y lo reprocesa solo.
  Future<void> _analyze(String caseId) async {
    _hub.notify();
    try {
      await _api.post('/cases/$caseId/submit', timeout: analysisTimeout);
    } on AppException {
      // El estado real se lee del backend en el siguiente refresco.
    } finally {
      _hub.notify();
    }
  }

  /// Envía en orden los casos guardados sin conexión (RF-02.4, RNF-08). Solo
  /// los del médico con sesión: nunca con la identidad de otro (N5).
  Future<void> flushOfflineQueue() async {
    if (_flushing || !_connectivity.isOnline) return;
    _flushing = true;
    try {
      for (final q in _myQueue()) {
        // La sesión pudo cerrarse o cambiar durante el envío.
        if (!q.belongsTo(_currentUid())) break;
        try {
          final c = await _register(q);
          await _store.resolve(q, c.id);
          _hub.notify();
          unawaited(_analyze(c.id));
        } on NetworkException {
          break;
        } on AppException catch (e) {
          // Rechazo del backend (p. ej. consentimiento revocado): queda en la
          // cola con el motivo visible y se reintenta en el siguiente envío.
          await _store.markFailed(q.requestId, e.message);
        }
      }
    } finally {
      _flushing = false;
      _hub.notify();
    }
  }

  @override
  Future<void> retryAnalysis(String caseId) async {
    if (!_connectivity.isOnline) {
      throw const AppException('Sin conexión. Se reintentará al recuperarla.');
    }
    try {
      await _api.post('/cases/$caseId/submit', timeout: analysisTimeout);
    } finally {
      _hub.notify();
    }
  }

  @override
  List<String> get manualOrder => List.unmodifiable(_store.manualOrder);

  @override
  Future<void> setManualOrder(List<String> caseIds) async {
    await _store.setManualOrder(caseIds);
    _hub.notify();
  }

  @override
  Future<void> updateSuggestion(String caseId, String suggestion) async {
    await _api.put('/cases/$caseId/suggestion', body: {'texto': suggestion.trim()});
    _hub.notify();
  }

  @override
  Future<void> addInternalNote(String caseId, String text) async {
    if (text.trim().isEmpty) throw const AppException('La observación está vacía.');
    await _api.post('/cases/$caseId/notes', body: {'texto': text.trim()});
    _hub.notify();
  }

  void dispose() => _connectivitySub.cancel();
}

/// Módulo Validación Clínica.
class RestValidationRepository implements ValidationRepository {
  RestValidationRepository(this._api, this._hub);

  final ApiClient _api;
  final RefreshHub _hub;

  @override
  Stream<List<ClinicalValidation>> watchValidations(String caseId) => _hub.watch(() async =>
      _list(await _api.get('/cases/$caseId/validations')).map(validationFromJson).toList());

  @override
  Future<ClinicalValidation> registerValidation({
    required String caseId,
    required ValidationDecision decision,
    required String sustentoClinico,
    String? examenesAdicionales,
    bool? sugerenciaTomada,
    LesionClass? claseFinal,
    String? complementaDe,
  }) async {
    final json = await _api.post('/validations', body: {
      'id_caso': caseId,
      'decision': decisionCodes[decision],
      'sustento_clinico': sustentoClinico.trim(),
      if (decision == ValidationDecision.corregir && claseFinal != null)
        'clase_final': lesionClassCodes[claseFinal],
      'examenes_adicionales': ?examenesAdicionales,
      'sugerencia_tomada': ?sugerenciaTomada,
      'complementa_de': ?complementaDe,
    });
    _hub.notify();
    return validationFromJson(json as Json);
  }
}

/// Módulo Informes (I9).
class RestReportRepository implements ReportRepository {
  RestReportRepository(this._api, this._hub, this._store, {Future<Directory> Function()? tempDir})
      : _tempDir = tempDir ?? (() async => Directory.systemTemp);

  final ApiClient _api;
  final RefreshHub _hub;
  final LocalCaseStore _store;
  final Future<Directory> Function() _tempDir;

  @override
  Stream<CaseReport?> watchReport(String caseId) => _hub.watch(() async {
        try {
          return reportFromDocumentJson(await _api.get('/reports/$caseId') as Json);
        } on AppException catch (e) {
          // Sin cierre todavía: el backend responde validation-required.
          if (e.code == 'validation-required' || e.code == 'not-found') return null;
          rethrow;
        }
      });

  @override
  Future<CaseReport> closeCase(String caseId, String conductaClinica) async {
    final json = await _api.post('/cases/$caseId/close',
        body: {'conducta_clinica': conductaClinica.trim()});
    _hub.notify();
    return reportFromJson(json as Json);
  }

  @override
  Future<ReportDocument> buildReportDocument(String caseId) async {
    final json = await _api.get('/reports/$caseId') as Json;
    final paths = Map.of(_store.localImages[caseId] ?? const <ImageView, String>{});
    // El informe no trae las fotos: si no hay copia local, se descargan con las
    // URL firmadas del detalle del caso.
    if (ImageView.values.any((v) => paths[v] == null || !File(paths[v]!).existsSync())) {
      try {
        final detail = caseFromJson(await _api.get('/cases/$caseId') as Json);
        final dir = await _tempDir();
        for (final image in [detail.foto1, detail.foto2]) {
          final url = image.remoteUrl;
          if (url == null) continue;
          final file = File('${dir.path}/dermavia_${caseId}_${imageViewCodes[image.view]}');
          await file.writeAsBytes(await _api.download(url));
          paths[image.view] = file.path;
        }
      } on AppException {
        // El caso es de otro médico (historial) o la foto no se pudo bajar:
        // el informe se genera sin fotos.
      }
    }
    return reportDocumentFromJson(json,
        foto1Path: paths[ImageView.foto1],
        foto2Path: paths[ImageView.foto2]);
  }
}
