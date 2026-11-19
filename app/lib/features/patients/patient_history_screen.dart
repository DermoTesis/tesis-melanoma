import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../core/widgets/common.dart';
import '../../domain/models/clinical_case.dart';
import '../../domain/models/patient.dart';
import '../../domain/models/prediction.dart';
import '../../domain/models/validation.dart';
import '../../providers/repository_providers.dart';
import 'patient_widgets.dart';

/// Pantalla 20 · Historial del paciente (HU28, RF-05.6).
class PatientHistoryScreen extends ConsumerWidget {
  const PatientHistoryScreen({super.key, required this.patientId});
  final String patientId;

  Future<void> _revoke(BuildContext context, WidgetRef ref, Patient p) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Registrar revocación'),
        content: Text(
            '${p.nombres} revoca su consentimiento informado. No podrán registrarse nuevos casos '
            'hasta que otorgue uno nuevo. El evento quedará en la bitácora.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
          TextButton(
            style: TextButton.styleFrom(foregroundColor: AppColors.error),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Registrar revocación'),
          ),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    try {
      await ref.read(patientRepositoryProvider).revokeConsent(p.id);
      if (context.mounted) showAppSnack(context, 'Revocación registrada.');
    } on AppException catch (e) {
      if (context.mounted) showAppSnack(context, e.message, error: true);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final patientAsync = ref.watch(patientProvider(patientId));
    final cases = ref.watch(patientCasesProvider(patientId)).value ?? const <ClinicalCase>[];
    final now = ref.watch(clockProvider)();

    return Scaffold(
      appBar: AppBar(title: const Text('Expediente')),
      body: patientAsync.when(
        loading: () => const LoadingView(),
        error: (e, _) => ErrorView('$e'),
        data: (p) {
          if (p == null) return const ErrorView('Paciente no encontrado.');
          final validated = cases
              .where((c) => c.status == CaseStatus.validado || c.status == CaseStatus.cerrado)
              .toList();
          final open = cases
              .where((c) => c.status != CaseStatus.validado && c.status != CaseStatus.cerrado)
              .toList();
          final consent = p.consent;
          return ListView(
            padding: const EdgeInsets.fromLTRB(18, 0, 18, 24),
            children: [
              PatientHeader(patient: p, now: now, big: true),
              const SizedBox(height: 4),
              Padding(
                padding: const EdgeInsets.only(left: 64),
                child: Text(p.numeroHistoriaClinica, style: AppFonts.mono(fontSize: 12)),
              ),
              const SizedBox(height: 16),
              PrimaryButton(
                label: 'Iniciar nuevo caso',
                icon: Icons.add_a_photo_outlined,
                onPressed: () => startCaseFor(context, ref, p),
              ),
              if (open.isNotEmpty) ...[
                const SizedBox(height: 20),
                const Text('Casos en curso',
                    style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: AppColors.textMuted)),
                const SizedBox(height: 8),
                for (final c in open)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: AppCard(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
                      onTap: () => context.push('/caso/${c.id}'),
                      child: Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(Fmt.date(c.createdAt), style: AppFonts.mono(fontSize: 12, color: AppColors.text)),
                                Text(c.clinicalData.ubicacionLesion,
                                    style: const TextStyle(fontSize: 13, color: AppColors.textMuted)),
                              ],
                            ),
                          ),
                          StatusChip(c.status.label,
                              tone: c.status == CaseStatus.errorAnalisis
                                  ? ChipTone.error
                                  : ChipTone.warning),
                        ],
                      ),
                    ),
                  ),
              ],
              const SizedBox(height: 20),
              const Text('Casos validados · más reciente primero',
                  style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: AppColors.textMuted)),
              const SizedBox(height: 8),
              if (validated.isEmpty)
                const InfoBanner(message: 'Aún no hay casos validados para este paciente.'),
              for (var i = 0; i < validated.length; i++)
                Padding(
                  padding: const EdgeInsets.only(bottom: 10),
                  child: _HistoryItem(clinicalCase: validated[i], expanded: i == 0),
                ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      consent == null
                          ? 'Sin consentimiento registrado'
                          : consent.vigente
                              ? 'Consentimiento vigente desde ${Fmt.date(consent.fechaOtorgamiento)}'
                              : 'Consentimiento revocado el ${Fmt.date(consent.fechaRevocacion!)}',
                      style: const TextStyle(fontSize: 12, color: AppColors.textSubtle),
                    ),
                  ),
                  if (consent?.vigente ?? false)
                    TextButton(
                      style: TextButton.styleFrom(foregroundColor: AppColors.error),
                      onPressed: () => _revoke(context, ref, p),
                      child: const Text('Revocar'),
                    )
                  else
                    TextButton(
                      onPressed: () => context.push('/paciente/${p.id}/consentimiento'),
                      child: const Text('Registrar'),
                    ),
                ],
              ),
            ],
          );
        },
      ),
    );
  }
}

class _HistoryItem extends ConsumerWidget {
  const _HistoryItem({required this.clinicalCase, required this.expanded});
  final ClinicalCase clinicalCase;
  final bool expanded;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = clinicalCase;
    final validations = ref.watch(validationsProvider(c.id)).value ?? const <ClinicalValidation>[];
    final v = validations.isEmpty ? null : validations.last;
    final p = c.prediction;
    final doctorLabel = v == null
        ? '—'
        : v.claseFinal == null
            ? 'Descartada'
            : '${v.claseFinal!.label} (${v.decision.pastLabel.toLowerCase()})';
    final statusChip = StatusChip(c.status.label,
        tone: c.status == CaseStatus.cerrado ? ChipTone.solid : ChipTone.success);

    if (!expanded) {
      return AppCard(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        onTap: () => context.push('/caso/${c.id}'),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(Fmt.date(c.createdAt), style: AppFonts.mono(fontSize: 12, color: AppColors.text)),
                  const SizedBox(height: 2),
                  Text('${c.clinicalData.ubicacionLesion.split(',').first} · $doctorLabel',
                      style: const TextStyle(fontSize: 13, color: AppColors.textMuted)),
                ],
              ),
            ),
            statusChip,
          ],
        ),
      );
    }

    return AppCard(
      padding: const EdgeInsets.all(14),
      onTap: () => context.push('/caso/${c.id}'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Text(Fmt.date(c.createdAt), style: AppFonts.mono(fontSize: 12, color: AppColors.text)),
              const Spacer(),
              statusChip,
            ],
          ),
          const SizedBox(height: 10),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              LesionThumbnail(path: c.foto2.localPath, url: c.foto2.remoteUrl, size: 64),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  children: [
                    DashedBorderBox(
                      radius: 8,
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                      child: _Labeled(
                        'MODELO',
                        p == null ? '—' : p.shortSummary,
                        AppColors.warningText,
                      ),
                    ),
                    const SizedBox(height: 6),
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                      decoration: BoxDecoration(
                          color: AppColors.successBg, borderRadius: BorderRadius.circular(8)),
                      child: _Labeled('MÉDICO', doctorLabel, AppColors.primaryDark, bold: true),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(c.clinicalData.ubicacionLesion,
              style: const TextStyle(fontSize: 12, color: AppColors.textSubtle)),
          if (p != null && v?.claseFinal != null && v!.claseFinal != p.clasePredicha)
            const Padding(
              padding: EdgeInsets.only(top: 4),
              child: Text('El especialista corrigió la predicción del modelo.',
                  style: TextStyle(fontSize: 12, color: AppColors.warningText)),
            ),
        ],
      ),
    );
  }
}

class _Labeled extends StatelessWidget {
  const _Labeled(this.label, this.value, this.color, {this.bold = false});
  final String label;
  final String value;
  final Color color;
  final bool bold;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: TextStyle(fontSize: 10, fontWeight: FontWeight.w700, color: color)),
        Text(value,
            style: TextStyle(
                fontSize: 12,
                fontWeight: bold ? FontWeight.w600 : FontWeight.w400,
                color: AppColors.text)),
      ],
    );
  }
}
