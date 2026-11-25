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
import 'transitions.dart';

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
      _page('/login', AppTransition.fadeThrough, (_) => const LoginScreen()),
      _page('/recuperar', AppTransition.step, (_) => const RecoverScreen()),
      _page('/activar/:uid', AppTransition.step,
          (s) => ActivationScreen(uid: s.pathParameters['uid']!)),
      _page('/alcance', AppTransition.fadeThrough, (_) => const ScopeAcceptanceScreen()),

      // --- Médico especialista ---
      StatefulShellRoute(
        pageBuilder: (_, s, shell) =>
            transitionPage(s, AppTransition.fadeThrough, HomeShell(shell: shell)),
        navigatorContainerBuilder: (_, shell, children) =>
            FadeThroughBranches(currentIndex: shell.currentIndex, children: children),
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
      // Registro de un caso, paso a paso.
      _page('/nuevo-caso', AppTransition.step, (_) => const PatientSearchScreen()),
      _page('/paciente/nuevo', AppTransition.step,
          (s) => RegisterPatientScreen(initialHc: s.uri.queryParameters['hc'])),
      _page('/paciente/:id', AppTransition.drillIn,
          (s) => PatientHistoryScreen(patientId: s.pathParameters['id']!)),
      _page('/paciente/:id/consentimiento', AppTransition.step,
          (s) => ConsentScreen(patientId: s.pathParameters['id']!)),
      _page('/captura/:patientId', AppTransition.step,
          (s) => CameraCaptureScreen(patientId: s.pathParameters['patientId']!)),
      _page('/captura/:patientId/galeria', AppTransition.step,
          (s) => GalleryReviewScreen(patientId: s.pathParameters['patientId']!)),
      _page('/captura/:patientId/datos', AppTransition.step,
          (s) => ClinicalDataScreen(patientId: s.pathParameters['patientId']!)),
      _page('/caso/:id', AppTransition.drillIn,
          (s) => CaseDetailScreen(caseId: s.pathParameters['id']!)),
      _page('/caso/:id/enviado', AppTransition.fadeThrough,
          (s) => CaseSubmittedScreen(caseId: s.pathParameters['id']!)),
      _page(
        '/caso/:id/validar',
        AppTransition.drillIn,
        (s) => ValidationFormScreen(
          caseId: s.pathParameters['id']!,
          complementaDe: s.uri.queryParameters['complementa'],
        ),
      ),
      _page('/caso/:id/informe', AppTransition.drillIn,
          (s) => ReportPreviewScreen(caseId: s.pathParameters['id']!)),

      // --- Administrador ---
      _page('/admin', AppTransition.fadeThrough, (_) => const AdminHomeScreen()),
      _page('/admin/nuevo', AppTransition.drillIn, (_) => const NewSpecialistScreen()),
      _page('/admin/bitacora', AppTransition.drillIn, (_) => const AuditLogScreen()),
    ],
  );
});

/// Ruta de nivel superior con su transición (ver [AppTransition]).
GoRoute _page(String path, AppTransition transition, Widget Function(GoRouterState) build) {
  return GoRoute(
    path: path,
    pageBuilder: (_, s) => transitionPage(s, transition, build(s)),
  );
}
