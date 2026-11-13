import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../domain/models/clinical_case.dart';
import 'repository_providers.dart';

/// Tiempo límite de validación configurado (RF-04.5).
const kValidationDeadline = Duration(hours: 48);

/// Borrador del caso en captura (panorámica + acercamiento).
class CaptureDraftNotifier extends Notifier<CaseDraft?> {
  @override
  CaseDraft? build() => null;

  void start(String patientId) {
    if (state?.patientId != patientId) state = CaseDraft(patientId: patientId);
  }

  void setDermatoscope(bool value) {
    final s = state;
    if (s != null) state = s.copyWith(conDermatoscopio: value);
  }

  void setImage(CaseImage image) {
    final s = state;
    if (s == null) return;
    state = image.view == ImageView.panoramica
        ? s.copyWith(panoramica: image)
        : s.copyWith(acercamiento: image);
  }

  void clearImage(ImageView view) {
    final s = state;
    if (s == null) return;
    state = view == ImageView.panoramica
        ? s.copyWith(clearPanoramica: true)
        : s.copyWith(clearAcercamiento: true);
  }

  void reset() => state = null;
}

final captureDraftProvider =
    NotifierProvider<CaptureDraftNotifier, CaseDraft?>(CaptureDraftNotifier.new);

/// Ordena los pendientes por probabilidad preliminar de malignidad
/// (descendente) salvo que el especialista haya fijado un orden manual
/// (RF-06.2).
List<ClinicalCase> sortForPanel(List<ClinicalCase> cases, List<String> manual) {
  final list = List.of(cases);
  if (manual.isNotEmpty) {
    int idx(ClinicalCase c) {
      final i = manual.indexOf(c.id);
      return i < 0 ? 1 << 20 : i;
    }

    list.sort((a, b) {
      final cmp = idx(a).compareTo(idx(b));
      if (cmp != 0) return cmp;
      return _byProbability(a, b);
    });
    return list;
  }
  list.sort(_byProbability);
  return list;
}

int _byProbability(ClinicalCase a, ClinicalCase b) {
  final pa = a.prediction?.probabilidadMalignidad ?? -1;
  final pb = b.prediction?.probabilidadMalignidad ?? -1;
  final cmp = pb.compareTo(pa);
  return cmp != 0 ? cmp : b.createdAt.compareTo(a.createdAt);
}

/// Casos pendientes de validación que superan el tiempo límite.
final overdueCasesProvider = Provider<List<ClinicalCase>>((ref) {
  final cases = ref.watch(myCasesProvider).value ?? const [];
  final now = ref.watch(clockProvider)();
  final overdue = cases
      .where((c) =>
          c.isPendingValidation && c.pendingFor(now) > kValidationDeadline)
      .toList()
    ..sort((a, b) => a.createdAt.compareTo(b.createdAt));
  return overdue;
});
