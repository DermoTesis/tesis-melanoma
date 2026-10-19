import 'dart:async';

import '../../core/errors/app_exception.dart';
import '../../domain/models/audit_event.dart';
import '../../domain/models/clinical_case.dart';
import '../../domain/models/patient.dart';
import '../../domain/models/report.dart';
import '../../domain/models/user.dart';
import '../../domain/models/validation.dart';
import 'mock_inference_engine.dart';
import 'seed_data.dart';

/// Estado en memoria que imita al backend (Cloud Run + Firestore +
/// Cloud Storage + Cloud Scheduler). Las reglas de negocio críticas se
/// aplican aquí, igual que lo haría el backend, para que la UI no pueda
/// saltarse la validación médica obligatoria (RF-07.1).
class MockBackend {
  MockBackend({
    DateTime Function()? clock,
    this.latency = const Duration(milliseconds: 350),
    this.analysisDuration = const Duration(seconds: 3),
    Duration? schedulerInterval = const Duration(seconds: 20),
    bool seed = true,
    MockInferenceEngine? inference,
  })  : _clock = clock ?? DateTime.now,
        inference =
            inference ?? MockInferenceEngine(failingCaseIds: {'CASO-0197'}) {
    if (seed) SeedData.apply(this);
    if (schedulerInterval != null) {
      _scheduler = Timer.periodic(schedulerInterval, (_) => runScheduledTasks());
    }
  }

  final DateTime Function() _clock;
  final Duration latency;
  final Duration analysisDuration;
  final MockInferenceEngine inference;
  Timer? _scheduler;

  // "Colecciones"
  final users = <String, AppUser>{};
  final passwords = <String, String>{};
  final activations = <String, ActivationTicket>{};
  final resets = <String, PasswordResetTicket>{};
  final patients = <String, Patient>{};
  final cases = <String, ClinicalCase>{};

  /// Colección de validaciones de solo inserción (Firestore validaciones).
  final validations = <String, List<ClinicalValidation>>{};
  final reports = <String, CaseReport>{};
  final audit = <AuditEvent>[];
  List<String> manualOrder = [];

  AppUser? session;
  bool online = true;
  int caseSequence = 200;
  int idSequence = 1000;

  final _changes = StreamController<void>.broadcast();
  final _connectivity = StreamController<bool>.broadcast();

  DateTime now() => _clock();
  String nextId(String prefix) => '$prefix-${idSequence++}';

  Future<void> delay() =>
      latency == Duration.zero ? Future.value() : Future.delayed(latency);

  void notify() {
    if (!_changes.isClosed) _changes.add(null);
  }

  /// Emite el valor actual y vuelve a emitir tras cada cambio, como un
  /// snapshot listener de Firestore.
  Stream<T> watch<T>(T Function() read) {
    late StreamController<T> controller;
    StreamSubscription<void>? sub;
    controller = StreamController<T>(
      onListen: () {
        controller.add(read());
        sub = _changes.stream.listen((_) => controller.add(read()));
      },
      onCancel: () => sub?.cancel(),
    );
    return controller.stream;
  }

  Stream<bool> connectivityChanges() => _connectivity.stream;

  void setOnline(bool value) {
    if (online == value) return;
    online = value;
    _connectivity.add(value);
    if (value) flushOfflineQueue();
    notify();
  }

  void log(AuditType type, String reference, {String? actor}) {
    audit.add(AuditEvent(
      id: nextId('EV'),
      type: type,
      reference: reference,
      actorName: actor ?? session?.nombres ?? 'Sistema',
      timestamp: now(),
    ));
  }

  // --- Autorización (equivalente a la validación del ID token y rol) ---

  AppUser requireSession() {
    final user = session;
    if (user == null) {
      throw const PermissionDeniedException('Tu sesión expiró. Inicia sesión otra vez.');
    }
    return user;
  }

  AppUser requireAdmin() {
    final user = requireSession();
    if (!user.isAdmin) throw const PermissionDeniedException();
    return user;
  }

  /// Solo especialistas activos, con acceso clínico y alcance aceptado.
  AppUser requireClinician() {
    final user = requireSession();
    final fresh = users[user.uid] ?? user;
    if (!fresh.isSpecialist || !fresh.clinicalAccess) {
      throw const PermissionDeniedException(
          'Tu cuenta no tiene acceso a funciones clínicas.');
    }
    if (fresh.needsScopeAcceptance) {
      throw const PermissionDeniedException(
          'Debes aceptar el alcance de apoyo diagnóstico antes de continuar.');
    }
    return fresh;
  }

  // --- Flujo del caso ---

  String nextCaseId() => 'CASO-${(++caseSequence).toString().padLeft(4, '0')}';

  void startAnalysis(String caseId) {
    final c = cases[caseId];
    if (c == null) return;
    cases[caseId] = c.copyWith(
      status: CaseStatus.enAnalisis,
      queuedOffline: false,
      analysisAttempts: c.analysisAttempts + 1,
    );
    notify();
    Future.delayed(analysisDuration, () => _completeAnalysis(caseId));
  }

  void _completeAnalysis(String caseId) {
    final c = cases[caseId];
    if (c == null || c.status != CaseStatus.enAnalisis) return;
    try {
      final prediction = inference.predict(c, now());
      cases[caseId] = c.copyWith(
        status: CaseStatus.pendienteValidacion,
        prediction: prediction,
        suggestion: prediction.defaultSuggestion,
      );
    } catch (_) {
      cases[caseId] = c.copyWith(status: CaseStatus.errorAnalisis);
    }
    notify();
  }

  void flushOfflineQueue() {
    final queued = cases.values
        .where((c) => c.queuedOffline && c.status == CaseStatus.registrado)
        .map((c) => c.id)
        .toList();
    for (final id in queued) {
      startAnalysis(id);
    }
  }

  /// Tarea periódica de Cloud Scheduler: reprocesa los casos con
  /// ERROR_ANALISIS (sección 3.4). Las alertas de casos vencidos se
  /// calculan a partir de la fecha de registro (RF-04.5).
  void runScheduledTasks() {
    if (!online) return;
    final failed = cases.values
        .where((c) => c.status == CaseStatus.errorAnalisis)
        .map((c) => c.id)
        .toList();
    for (final id in failed) {
      startAnalysis(id);
    }
  }

  void dispose() {
    _scheduler?.cancel();
    _changes.close();
    _connectivity.close();
  }
}
