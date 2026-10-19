import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/mock/mock_backend.dart';
import '../data/mock/mock_repositories.dart';
import '../domain/models/audit_event.dart';
import '../domain/models/clinical_case.dart';
import '../domain/models/patient.dart';
import '../domain/models/report.dart';
import '../domain/models/user.dart';
import '../domain/models/validation.dart';
import '../domain/repositories/repositories.dart';

// Único punto de cambio entre las implementaciones simuladas y las reales.
// Para conectar el backend en Cloud Run y Firebase, reemplazar cada
// Mock*Repository por su implementación REST/Firebase.

final mockBackendProvider = Provider<MockBackend>((ref) {
  final backend = MockBackend();
  ref.onDispose(backend.dispose);
  return backend;
});

final authRepositoryProvider = Provider<AuthRepository>(
    (ref) => MockAuthRepository(ref.watch(mockBackendProvider)));
final adminRepositoryProvider = Provider<AdminRepository>(
    (ref) => MockAdminRepository(ref.watch(mockBackendProvider)));
final patientRepositoryProvider = Provider<PatientRepository>(
    (ref) => MockPatientRepository(ref.watch(mockBackendProvider)));
final caseRepositoryProvider = Provider<CaseRepository>(
    (ref) => MockCaseRepository(ref.watch(mockBackendProvider)));
final validationRepositoryProvider = Provider<ValidationRepository>(
    (ref) => MockValidationRepository(ref.watch(mockBackendProvider)));
final reportRepositoryProvider = Provider<ReportRepository>(
    (ref) => MockReportRepository(ref.watch(mockBackendProvider)));
final auditRepositoryProvider = Provider<AuditRepository>(
    (ref) => MockAuditRepository(ref.watch(mockBackendProvider)));
final connectivityServiceProvider = Provider<ConnectivityService>(
    (ref) => MockConnectivityService(ref.watch(mockBackendProvider)));

/// Reloj de la aplicación (inyectable para pruebas).
final clockProvider =
    Provider<DateTime Function()>((ref) => ref.watch(mockBackendProvider).now);

// --- Flujos de lectura ---

final authStateProvider = StreamProvider<AppUser?>(
    (ref) => ref.watch(authRepositoryProvider).authStateChanges());

final onlineProvider = StreamProvider<bool>(
    (ref) => ref.watch(connectivityServiceProvider).onlineChanges());

final myCasesProvider = StreamProvider<List<ClinicalCase>>((ref) {
  // Se reconstruye al cambiar la sesión.
  ref.watch(authStateProvider.select((s) => s.value?.uid));
  return ref.watch(caseRepositoryProvider).watchMyCases();
});

final caseProvider = StreamProvider.family<ClinicalCase?, String>(
    (ref, id) => ref.watch(caseRepositoryProvider).watchCase(id));

final patientCasesProvider = StreamProvider.family<List<ClinicalCase>, String>(
    (ref, patientId) =>
        ref.watch(caseRepositoryProvider).watchCasesForPatient(patientId));

final patientsProvider = StreamProvider<List<Patient>>(
    (ref) => ref.watch(patientRepositoryProvider).watchPatients());

final patientProvider = StreamProvider.family<Patient?, String>(
    (ref, id) => ref.watch(patientRepositoryProvider).watchPatient(id));

final validationsProvider =
    StreamProvider.family<List<ClinicalValidation>, String>((ref, caseId) =>
        ref.watch(validationRepositoryProvider).watchValidations(caseId));

final reportProvider = StreamProvider.family<CaseReport?, String>(
    (ref, caseId) => ref.watch(reportRepositoryProvider).watchReport(caseId));

final usersProvider = StreamProvider<List<AppUser>>(
    (ref) => ref.watch(adminRepositoryProvider).watchUsers());

final auditEventsProvider = StreamProvider<List<AuditEvent>>(
    (ref) => ref.watch(auditRepositoryProvider).watchEvents());
