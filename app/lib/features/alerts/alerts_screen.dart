import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../core/widgets/common.dart';
import '../../domain/models/patient.dart';
import '../../domain/models/prediction.dart';
import '../../providers/case_providers.dart';
import '../../providers/repository_providers.dart';
import '../dashboard/case_widgets.dart';

/// Pantalla 06 · Alertas de casos vencidos sin validación (HU24, RF-04.5).
class AlertsScreen extends ConsumerWidget {
  const AlertsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final overdue = ref.watch(overdueCasesProvider);
    final patients = {
      for (final p in ref.watch(patientsProvider).value ?? const <Patient>[]) p.id: p
    };
    final now = ref.watch(clockProvider)();

    return Scaffold(
      body: Column(
        children: [
          const SafeArea(bottom: false, child: OfflineBanner()),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(18, 14, 18, 24),
              children: [
                const Text('Alertas',
                    style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
                const SizedBox(height: 14),
                Text(
                  'Casos que registraste y siguen sin validar tras el tiempo límite '
                  'configurado (${kValidationDeadline.inHours} h). El administrador también ve estas alertas.',
                  style: const TextStyle(fontSize: 14, height: 1.45, color: AppColors.textMuted),
                ),
                const SizedBox(height: 16),
                for (final c in overdue) ...[
                  AppCard(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Row(
                          children: [
                            StatusChip(
                              'Vencido hace ${Fmt.duration(c.pendingFor(now) - kValidationDeadline)}',
                              tone: ChipTone.error,
                            ),
                            const Spacer(),
                            Text(c.id, style: AppFonts.mono(fontSize: 11)),
                          ],
                        ),
                        const SizedBox(height: 10),
                        Text(patients[c.patientId]?.nombres ?? '—',
                            style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 16)),
                        const SizedBox(height: 6),
                        Text(
                          'Registrado ${Fmt.dayMonth(c.createdAt)} · ${Fmt.time(c.createdAt)} · '
                          'Prob. preliminar ${_level(c.prediction)}',
                          style: const TextStyle(fontSize: 13, color: AppColors.textMuted),
                        ),
                        const SizedBox(height: 12),
                        SizedBox(
                          height: 44,
                          child: c == overdue.first
                              ? FilledButton(
                                  style: FilledButton.styleFrom(
                                      minimumSize: const Size.fromHeight(44),
                                      shape: RoundedRectangleBorder(
                                          borderRadius: BorderRadius.circular(12))),
                                  onPressed: () => context.push('/caso/${c.id}'),
                                  child: const Text('Revisar ahora'),
                                )
                              : OutlinedButton(
                                  style: OutlinedButton.styleFrom(
                                      minimumSize: const Size.fromHeight(44),
                                      shape: RoundedRectangleBorder(
                                          borderRadius: BorderRadius.circular(12))),
                                  onPressed: () => context.push('/caso/${c.id}'),
                                  child: const Text('Revisar'),
                                ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 10),
                ],
                if (overdue.isEmpty)
                  const InfoBanner(
                    tone: BannerTone.success,
                    message: 'No tienes casos vencidos. ¡Todo al día!',
                  ),
                const SizedBox(height: 4),
                const InfoBanner(
                    message: 'Los casos validados dentro del plazo no generan alertas.'),
              ],
            ),
          ),
        ],
      ),
    );
  }

  static String _level(Prediction? p) {
    if (p == null) return '—';
    return switch (p.confidence) {
      PredictionConfidence.alta => 'alta',
      PredictionConfidence.ambigua => 'media',
      PredictionConfidence.baja => 'baja',
      PredictionConfidence.benigna => 'bajo el umbral',
    };
  }
}
