import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../features/admin/admin_home_screen.dart';
import '../../features/admin/audit_log_screen.dart';
import '../../features/admin/new_specialist_screen.dart';
import '../../features/alerts/alerts_screen.dart';
import '../../features/auth/activation_screen.dart';
import '../../features/auth/login_screen.dart';
import '../../features/auth/recover_screen.dart';
import '../../features/auth/scope_acceptance_screen.dart';
import '../../features/capture/camera_capture_screen.dart';
import '../../features/capture/clinical_data_screen.dart';
import '../../features/capture/gallery_review_screen.dart';
import '../../features/case_review/case_detail_screen.dart';
import '../../features/case_review/case_submitted_screen.dart';
import '../../features/dashboard/cases_panel_screen.dart';
import '../../features/dashboard/home_shell.dart';
import '../../features/patients/consent_screen.dart';
import '../../features/patients/patient_history_screen.dart';
import '../../features/patients/patient_search_screen.dart';
import '../../features/patients/patients_screen.dart';
import '../../features/patients/register_patient_screen.dart';
import '../../features/profile/profile_screen.dart';
import '../../features/reports/report_preview_screen.dart';
import '../../features/validation/validation_form_screen.dart';
import '../../providers/repository_providers.dart';

class _AuthRefresh extends ChangeNotifier {
  _AuthRefresh(Ref ref) {
    ref.listen(authStateProvider, (_, _) => notifyListeners());
  }
}

final rootNavigatorKey = GlobalKey<NavigatorState>();

final routerProvider = Provider<GoRouter>((ref) {
  final refresh = _AuthRefresh(ref);
  ref.onDispose(refresh.dispose);

  return GoRouter(
    navigatorKey: rootNavigatorKey,
    initialLocation: '/casos',
    refreshListenable: refresh,
    redirect: (context, state) {
      final user = ref.read(authRepositoryProvider).currentUser;
      final loc = state.matchedLocation;
      final isPublic = loc == '/login' ||
          loc.startsWith('/recuperar') ||
          loc.startsWith('/activar');

      if (user == null) return isPublic ? null : '/login';
      // Aceptación del alcance obligatoria en el primer acceso (RF-05.3).
      if (user.needsScopeAcceptance) return loc == '/alcance' ? null : '/alcance';
      // Acceso por rol (RNF-03).
      if (user.isAdmin) return loc.startsWith('/admin') ? null : '/admin';
      if (isPublic || loc == '/alcance' || loc.startsWith('/admin')) return '/casos';
      return null;
    },
    routes: [
      GoRoute(path: '/login', builder: (_, _) => const LoginScreen()),
      GoRoute(path: '/recuperar', builder: (_, _) => const RecoverScreen()),
      GoRoute(
        path: '/activar/:uid',
        builder: (_, s) => ActivationScreen(uid: s.pathParameters['uid']!),
      ),
      GoRoute(path: '/alcance', builder: (_, _) => const ScopeAcceptanceScreen()),

      // --- Médico especialista ---
      StatefulShellRoute.indexedStack(
        builder: (_, _, shell) => HomeShell(shell: shell),
        branches: [
          StatefulShellBranch(routes: [
            GoRoute(path: '/casos', builder: (_, _) => const CasesPanelScreen()),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(path: '/pacientes', builder: (_, _) => const PatientsScreen()),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(path: '/alertas', builder: (_, _) => const AlertsScreen()),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(path: '/perfil', builder: (_, _) => const ProfileScreen()),
          ]),
        ],
      ),
      GoRoute(path: '/nuevo-caso', builder: (_, _) => const PatientSearchScreen()),
      GoRoute(
        path: '/paciente/nuevo',
        builder: (_, s) => RegisterPatientScreen(initialHc: s.uri.queryParameters['hc']),
      ),
      GoRoute(
        path: '/paciente/:id',
        builder: (_, s) => PatientHistoryScreen(patientId: s.pathParameters['id']!),
      ),
      GoRoute(
        path: '/paciente/:id/consentimiento',
        builder: (_, s) => ConsentScreen(patientId: s.pathParameters['id']!),
      ),
      GoRoute(
        path: '/captura/:patientId',
        builder: (_, s) => CameraCaptureScreen(patientId: s.pathParameters['patientId']!),
      ),
      GoRoute(
        path: '/captura/:patientId/galeria',
        builder: (_, s) => GalleryReviewScreen(patientId: s.pathParameters['patientId']!),
      ),
      GoRoute(
        path: '/captura/:patientId/datos',
        builder: (_, s) => ClinicalDataScreen(patientId: s.pathParameters['patientId']!),
      ),
      GoRoute(
        path: '/caso/:id',
        builder: (_, s) => CaseDetailScreen(caseId: s.pathParameters['id']!),
      ),
      GoRoute(
        path: '/caso/:id/enviado',
        builder: (_, s) => CaseSubmittedScreen(caseId: s.pathParameters['id']!),
      ),
      GoRoute(
        path: '/caso/:id/validar',
        builder: (_, s) => ValidationFormScreen(
          caseId: s.pathParameters['id']!,
          complementaDe: s.uri.queryParameters['complementa'],
        ),
      ),
      GoRoute(
        path: '/caso/:id/informe',
        builder: (_, s) => ReportPreviewScreen(caseId: s.pathParameters['id']!),
      ),

      // --- Administrador ---
      GoRoute(path: '/admin', builder: (_, _) => const AdminHomeScreen()),
      GoRoute(path: '/admin/nuevo', builder: (_, _) => const NewSpecialistScreen()),
      GoRoute(path: '/admin/bitacora', builder: (_, _) => const AuditLogScreen()),
    ],
  );
});
