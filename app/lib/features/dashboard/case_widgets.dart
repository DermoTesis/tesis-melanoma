import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../core/widgets/common.dart';
import '../../domain/models/clinical_case.dart';
import '../../domain/models/patient.dart';
import '../../domain/models/prediction.dart';
import '../../providers/case_providers.dart';
import '../../providers/repository_providers.dart';

/// Tarjeta de caso del panel (pantalla 05).
class CaseCard extends StatelessWidget {
  const CaseCard({
    super.key,
    required this.clinicalCase,
    required this.patient,
    required this.now,
    this.onTap,
    this.trailing,
  });

  final ClinicalCase clinicalCase;
  final Patient? patient;
  final DateTime now;
  final VoidCallback? onTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final c = clinicalCase;
    final p = c.prediction;
    final overdue = c.isPendingValidation && c.pendingFor(now) > kValidationDeadline;
    final highRisk = overdue && p != null && p.clasePredicha == LesionClass.maligno;
    final isError = c.status == CaseStatus.errorAnalisis;

    final chip = switch (c.status) {
      CaseStatus.pendienteValidacion when overdue =>
        StatusChip(Fmt.duration(c.pendingFor(now)), tone: ChipTone.error),
      CaseStatus.pendienteValidacion => const StatusChip('Pendiente', tone: ChipTone.warning),
      CaseStatus.errorAnalisis => const StatusChip('Error', tone: ChipTone.error),
      CaseStatus.registrado => StatusChip(c.queuedOffline ? 'En cola' : 'Registrado'),
      CaseStatus.enAnalisis => const StatusChip('En análisis'),
      CaseStatus.validado => const StatusChip('Validado', tone: ChipTone.success),
      CaseStatus.cerrado => const StatusChip('Cerrado', tone: ChipTone.solid),
    };

    final (detail, detailColor) = _detail(c, p);

    return AppCard(
      onTap: onTap,
      padding: const EdgeInsets.all(12),
      color: highRisk ? AppColors.errorSurface : Colors.white,
      border: highRisk ? Border.all(color: AppColors.errorCardBorder, width: 1.5) : null,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (isError)
            Container(
              width: 52,
              height: 52,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                  color: AppColors.surfaceMuted, borderRadius: BorderRadius.circular(10)),
              child: const Text('!',
                  style: TextStyle(color: AppColors.error, fontWeight: FontWeight.w700)),
            )
          else
            LesionThumbnail(path: c.foto2.localPath, size: 52),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(patient?.shortName ?? '—',
                          overflow: TextOverflow.ellipsis,
                          style:
                              const TextStyle(fontWeight: FontWeight.w600, fontSize: 15)),
                    ),
                    chip,
                  ],
                ),
                const SizedBox(height: 4),
                if (!isError)
                  Text(
                    '${patient?.numeroHistoriaClinica ?? ''} · ${_shortSite(c.clinicalData.ubicacionLesion)}',
                    overflow: TextOverflow.ellipsis,
                    style: AppFonts.mono(fontSize: 11),
                  ),
                const SizedBox(height: 4),
                Text(detail,
                    style: TextStyle(
                        fontSize: 12,
                        height: 1.35,
                        fontWeight: isError ? FontWeight.w400 : FontWeight.w600,
                        color: detailColor)),
              ],
            ),
          ),
          if (trailing != null) ...[const SizedBox(width: 6), trailing!],
        ],
      ),
    );
  }

  static String _shortSite(String s) => s.split(',').first;

  static (String, Color) _detail(ClinicalCase c, Prediction? p) {
    switch (c.status) {
      case CaseStatus.errorAnalisis:
        return ('Error de análisis. Se reprocesará automáticamente.', AppColors.textMuted);
      case CaseStatus.registrado:
        return (
          c.queuedOffline ? 'Guardado sin conexión · se enviará al reconectar' : 'Enviando a análisis…',
          AppColors.textMuted
        );
      case CaseStatus.enAnalisis:
        return ('Generando predicción preliminar…', AppColors.textMuted);
      case CaseStatus.validado:
      case CaseStatus.cerrado:
      case CaseStatus.pendienteValidacion:
        if (p == null) return ('Sin predicción', AppColors.textMuted);
        final label = '${p.shortSummary} (${p.riskLevel})';
        if (c.status != CaseStatus.pendienteValidacion) {
          return ('Modelo: ${p.shortSummary}', AppColors.textMuted);
        }
        final color = switch (p.confidence) {
          PredictionConfidence.alta => AppColors.errorText,
          PredictionConfidence.ambigua || PredictionConfidence.baja => AppColors.warningText,
          PredictionConfidence.benigna => AppColors.textBody,
        };
        return (label, color);
    }
  }
}

/// Barra superior oscura "Sin conexión · modo degradado" (RNF-08).
class OfflineBanner extends ConsumerWidget {
  const OfflineBanner({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final online = ref.watch(onlineProvider).value ?? true;
    if (online) return const SizedBox.shrink();
    final queued = (ref.watch(myCasesProvider).value ?? const [])
        .where((c) => c.queuedOffline)
        .length;
    return Container(
      width: double.infinity,
      color: AppColors.ink,
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
      child: Row(
        children: [
          const Expanded(
            child: Text('Sin conexión · modo degradado',
                style: TextStyle(color: Colors.white, fontSize: 12)),
          ),
          if (queued > 0)
            Text('$queued caso${queued == 1 ? '' : 's'} en cola',
                style: const TextStyle(color: Color(0xFF9FD4BB), fontSize: 12)),
        ],
      ),
    );
  }
}
