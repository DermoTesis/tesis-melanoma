import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../core/widgets/common.dart';
import '../../domain/models/clinical_case.dart';
import '../../providers/repository_providers.dart';
import '../dashboard/case_widgets.dart';

/// Pantalla 14 · Caso enviado o guardado sin conexión (HU12, RF-02.4, RNF-08).
class CaseSubmittedScreen extends ConsumerWidget {
  const CaseSubmittedScreen({super.key, required this.caseId});
  final String caseId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final caseAsync = ref.watch(caseProvider(caseId));
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) context.go('/casos');
      },
      child: Scaffold(
        body: Column(
          children: [
            const SafeArea(bottom: false, child: OfflineBanner()),
            Expanded(
              child: caseAsync.when(
                loading: () => const LoadingView(),
                error: (e, _) => ErrorView('$e'),
                data: (c) => c == null
                    ? const ErrorView('Caso no encontrado.')
                    : _Body(clinicalCase: c),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Body extends ConsumerWidget {
  const _Body({required this.clinicalCase});
  final ClinicalCase clinicalCase;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = clinicalCase;
    final patient = ref.watch(patientProvider(c.patientId)).value;
    final (title, subtitle) = switch (c.status) {
      CaseStatus.registrado when c.queuedOffline => (
          'Caso guardado en el dispositivo',
          'Se enviará a análisis en cuanto vuelva la conexión. Puedes seguir atendiendo.'
        ),
      CaseStatus.registrado || CaseStatus.enAnalisis => (
          'Caso enviado a análisis',
          'El modelo está generando la predicción preliminar. Puedes seguir atendiendo.'
        ),
      CaseStatus.errorAnalisis => (
          'Error de análisis',
          'El análisis falló. Se reprocesará automáticamente.'
        ),
      CaseStatus.pendienteValidacion => (
          'Predicción preliminar lista',
          'Revisa la predicción y registra tu validación clínica.'
        ),
      CaseStatus.validado || CaseStatus.cerrado => (
          'Caso validado',
          'El caso ya cuenta con validación médica.'
        ),
    };

    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(22, 28, 22, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('${Fmt.caseId(c.id)} · ${patient?.numeroHistoriaClinica ?? ''}',
                style: AppFonts.mono(fontSize: 12)),
            const SizedBox(height: 8),
            Text(title,
                style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700, height: 1.2)),
            const SizedBox(height: 8),
            Text(subtitle,
                style: const TextStyle(fontSize: 15, height: 1.45, color: AppColors.textMuted)),
            const SizedBox(height: 22),
            AppCard(padding: const EdgeInsets.all(18), child: CaseTimeline(clinicalCase: c)),
            const Spacer(),
            if (c.status == CaseStatus.pendienteValidacion) ...[
              PrimaryButton(
                label: 'Revisar predicción',
                onPressed: () => context.push('/caso/${c.id}'),
              ),
              const SizedBox(height: 10),
              SecondaryButton(label: 'Volver al panel', onPressed: () => context.go('/casos')),
            ] else
              PrimaryButton(label: 'Volver al panel', onPressed: () => context.go('/casos')),
          ],
        ),
      ),
    );
  }
}

enum _StepState { done, current, error, pending }

/// Línea de tiempo con los cinco estados del flujo obligatorio.
class CaseTimeline extends StatelessWidget {
  const CaseTimeline({super.key, required this.clinicalCase});
  final ClinicalCase clinicalCase;

  @override
  Widget build(BuildContext context) {
    final c = clinicalCase;
    final s = c.status;
    final afterAnalysis = s == CaseStatus.pendienteValidacion ||
        s == CaseStatus.validado ||
        s == CaseStatus.cerrado;

    final steps = <(String, String?, _StepState)>[
      ('Registrado', '${Fmt.time(c.createdAt)} · 2 imágenes + datos clínicos', _StepState.done),
      c.queuedOffline
          ? ('En cola de envío', 'Esperando conexión', _StepState.current)
          : ('Enviado', null, s == CaseStatus.registrado ? _StepState.current : _StepState.done),
      (
        'En análisis · predicción preliminar',
        s == CaseStatus.errorAnalisis
            ? 'Error · se reprocesará automáticamente'
            : s == CaseStatus.enAnalisis
                ? 'Procesando…'
                : null,
        switch (s) {
          CaseStatus.enAnalisis => _StepState.current,
          CaseStatus.errorAnalisis => _StepState.error,
          _ when afterAnalysis => _StepState.done,
          _ => _StepState.pending,
        }
      ),
      (
        'Validación médica',
        s == CaseStatus.pendienteValidacion ? 'Pendiente de tu revisión' : null,
        s == CaseStatus.pendienteValidacion
            ? _StepState.current
            : (s == CaseStatus.validado || s == CaseStatus.cerrado)
                ? _StepState.done
                : _StepState.pending
      ),
      (
        'Cierre e informe',
        null,
        s == CaseStatus.cerrado
            ? _StepState.done
            : s == CaseStatus.validado
                ? _StepState.current
                : _StepState.pending
      ),
    ];

    return Column(
      children: [
        for (var i = 0; i < steps.length; i++)
          _TimelineRow(
            title: steps[i].$1,
            subtitle: steps[i].$2,
            state: steps[i].$3,
            last: i == steps.length - 1,
          ),
      ],
    );
  }
}

class _TimelineRow extends StatelessWidget {
  const _TimelineRow({
    required this.title,
    required this.subtitle,
    required this.state,
    required this.last,
  });

  final String title;
  final String? subtitle;
  final _StepState state;
  final bool last;

  @override
  Widget build(BuildContext context) {
    final dot = switch (state) {
      _StepState.done => Container(
          width: 22,
          height: 22,
          decoration: const BoxDecoration(color: AppColors.primary, shape: BoxShape.circle),
          child: const Icon(Icons.check, size: 14, color: Colors.white),
        ),
      _StepState.current => Container(
          width: 22,
          height: 22,
          decoration: BoxDecoration(
            color: AppColors.warningChip,
            shape: BoxShape.circle,
            border: Border.all(color: AppColors.warningAccent, width: 2),
          ),
        ),
      _StepState.error => Container(
          width: 22,
          height: 22,
          alignment: Alignment.center,
          decoration: const BoxDecoration(color: AppColors.error, shape: BoxShape.circle),
          child: const Text('!', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700)),
        ),
      _StepState.pending => Container(
          width: 22,
          height: 22,
          decoration: BoxDecoration(
              shape: BoxShape.circle, border: Border.all(color: AppColors.iconMuted, width: 2)),
        ),
    };
    final active = state != _StepState.pending;
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Column(
            children: [
              dot,
              if (!last)
                Expanded(
                  child: Container(
                    width: 2,
                    constraints: const BoxConstraints(minHeight: 18),
                    color: state == _StepState.done ? AppColors.primary : AppColors.border,
                  ),
                ),
            ],
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(top: 1, bottom: last ? 0 : 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title,
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: active ? FontWeight.w600 : FontWeight.w400,
                        color: active ? AppColors.text : AppColors.textSubtle,
                      )),
                  if (subtitle != null)
                    Text(subtitle!,
                        style: TextStyle(
                          fontSize: 12,
                          color: switch (state) {
                            _StepState.current => AppColors.warningText,
                            _StepState.error => AppColors.errorText,
                            _ => AppColors.textSubtle,
                          },
                        )),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
