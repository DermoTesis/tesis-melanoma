import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../core/utils/navigation.dart';
import '../../core/widgets/common.dart';
import '../../domain/models/clinical_case.dart';
import '../../domain/models/patient.dart';
import '../../domain/models/prediction.dart';
import '../../providers/repository_providers.dart';
import '../validation/validated_case_view.dart';
import 'case_submitted_screen.dart';

/// Detalle del caso: muestra la vista que corresponde a su estado.
class CaseDetailScreen extends ConsumerWidget {
  const CaseDetailScreen({super.key, required this.caseId});
  final String caseId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final caseAsync = ref.watch(caseProvider(caseId));
    final c = caseAsync.value;
    final chip = c == null
        ? null
        : switch (c.status) {
            CaseStatus.pendienteValidacion => const StatusChip('Pendiente', tone: ChipTone.warning),
            CaseStatus.validado => const StatusChip('Validado', tone: ChipTone.solid),
            CaseStatus.cerrado => const StatusChip('Cerrado', tone: ChipTone.solid),
            CaseStatus.errorAnalisis => const StatusChip('Error', tone: ChipTone.error),
            _ => StatusChip(c.status.label),
          };

    return Scaffold(
      appBar: AppBar(
        leading: const SmartBackButton(),
        title: Text(Fmt.caseId(caseId)),
        actions: [if (chip != null) Padding(padding: const EdgeInsets.only(right: 16), child: chip)],
      ),
      body: caseAsync.when(
        loading: () => const LoadingView(),
        error: (e, _) => ErrorView('$e'),
        data: (c) {
          if (c == null) return const ErrorView('Caso no encontrado.');
          return switch (c.status) {
            CaseStatus.registrado => _TimelineView(clinicalCase: c),
            CaseStatus.enAnalisis => _ProcessingView(clinicalCase: c),
            CaseStatus.errorAnalisis => _ErrorView(clinicalCase: c),
            CaseStatus.pendienteValidacion => _ReviewView(clinicalCase: c),
            CaseStatus.validado || CaseStatus.cerrado => ValidatedCaseView(clinicalCase: c),
          };
        },
      ),
    );
  }
}

class CaseImagesRow extends StatelessWidget {
  const CaseImagesRow({super.key, required this.clinicalCase, this.height = 124});
  final ClinicalCase clinicalCase;
  final double height;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: GestureDetector(
            onTap: () => _openImage(context, clinicalCase.foto1),
            child: LesionThumbnail(
              path: clinicalCase.foto1.localPath,
              url: clinicalCase.foto1.remoteUrl,
              height: height,
              radius: 14,
              dark: true,
              label: 'foto 1',
            ),
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: GestureDetector(
            onTap: () => _openImage(context, clinicalCase.foto2),
            child: LesionThumbnail(
              path: clinicalCase.foto2.localPath,
              url: clinicalCase.foto2.remoteUrl,
              height: height,
              radius: 14,
              dark: true,
              label: 'foto 2',
            ),
          ),
        ),
      ],
    );
  }

  void _openImage(BuildContext context, CaseImage image) {
    if (image.localPath == null && image.remoteUrl == null) return;
    showDialog<void>(
      context: context,
      builder: (ctx) => Dialog(
        insetPadding: const EdgeInsets.all(12),
        backgroundColor: Colors.black,
        child: Stack(
          children: [
            InteractiveViewer(
              child: LesionThumbnail(
                  path: image.localPath, url: image.remoteUrl, height: 480, radius: 16),
            ),
            Positioned(
              right: 4,
              top: 4,
              child: IconButton(
                icon: const Icon(Icons.close, color: Colors.white),
                onPressed: () => Navigator.pop(ctx),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TimelineView extends StatelessWidget {
  const _TimelineView({required this.clinicalCase});
  final ClinicalCase clinicalCase;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
      children: [
        CaseImagesRow(clinicalCase: clinicalCase, height: 180),
        const SizedBox(height: 16),
        AppCard(padding: const EdgeInsets.all(18), child: CaseTimeline(clinicalCase: clinicalCase)),
      ],
    );
  }
}

/// Pantalla 15 · Caso en procesamiento: la validación aún no está disponible.
class _ProcessingView extends StatelessWidget {
  const _ProcessingView({required this.clinicalCase});
  final ClinicalCase clinicalCase;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            CaseImagesRow(clinicalCase: clinicalCase, height: 220),
            const SizedBox(height: 18),
            const AppCard(
              padding: EdgeInsets.all(18),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: Text('En análisis',
                            style: TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
                      ),
                      Text('~ 20 s', style: TextStyle(fontSize: 12, color: AppColors.textSubtle)),
                    ],
                  ),
                  SizedBox(height: 14),
                  ClipRRect(
                    borderRadius: BorderRadius.all(Radius.circular(4)),
                    child: LinearProgressIndicator(minHeight: 8),
                  ),
                  SizedBox(height: 14),
                  Text(
                    'El modelo está generando la predicción preliminar. La validación se habilitará cuando termine.',
                    style: TextStyle(fontSize: 14, height: 1.45, color: AppColors.textMuted),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            const InfoBanner(
              message: 'Validación no disponible todavía',
              leading: Icon(Icons.lock_outline, size: 18, color: AppColors.textDisabled),
            ),
            const Spacer(),
            const PrimaryButton(label: 'Validar caso', onPressed: null),
          ],
        ),
      ),
    );
  }
}

class _ErrorView extends ConsumerStatefulWidget {
  const _ErrorView({required this.clinicalCase});
  final ClinicalCase clinicalCase;

  @override
  ConsumerState<_ErrorView> createState() => _ErrorViewState();
}

class _ErrorViewState extends ConsumerState<_ErrorView> {
  bool _retrying = false;

  Future<void> _retry() async {
    setState(() => _retrying = true);
    try {
      await ref.read(caseRepositoryProvider).retryAnalysis(widget.clinicalCase.id);
    } on AppException catch (e) {
      if (mounted) showAppSnack(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _retrying = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            CaseImagesRow(clinicalCase: widget.clinicalCase, height: 180),
            const SizedBox(height: 18),
            InfoBanner(
              tone: BannerTone.error,
              title: 'Error de análisis',
              leading: const AlertDot(),
              message: widget.clinicalCase.lastError ??
                  'El servicio de inferencia no respondió. Una tarea periódica lo reprocesará automáticamente; también puedes reintentar ahora.',
            ),
            const Spacer(),
            PrimaryButton(label: 'Reintentar ahora', loading: _retrying, onPressed: _retry),
          ],
        ),
      ),
    );
  }
}

/// Pantalla 16 · Revisión consolidada del caso (HU20, HU29, RF-04.1, RF-06.1).
class _ReviewView extends ConsumerWidget {
  const _ReviewView({required this.clinicalCase});
  final ClinicalCase clinicalCase;

  Future<void> _editSuggestion(BuildContext context, WidgetRef ref) async {
    final controller = TextEditingController(text: clinicalCase.suggestion ?? '');
    final result = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Sugerencia de exámenes'),
        content: TextField(
          controller: controller,
          maxLines: 5,
          minLines: 3,
          decoration: const InputDecoration(hintText: 'Exámenes adicionales sugeridos'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancelar')),
          TextButton(onPressed: () => Navigator.pop(ctx, controller.text), child: const Text('Guardar')),
        ],
      ),
    );
    if (result == null) return;
    try {
      await ref.read(caseRepositoryProvider).updateSuggestion(clinicalCase.id, result);
    } on AppException catch (e) {
      if (context.mounted) showAppSnack(context, e.message, error: true);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final c = clinicalCase;
    final p = c.prediction!;
    final patient = ref.watch(patientProvider(c.patientId)).value;
    final now = ref.watch(clockProvider)();

    return Column(
      children: [
        Expanded(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(18, 0, 18, 18),
            children: [
              CaseImagesRow(clinicalCase: c),
              const SizedBox(height: 12),
              if (patient != null)
                AppCard(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  onTap: () => context.push('/paciente/${patient.id}'),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(patient.shortName,
                            style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
                      ),
                      Text(
                        '${patient.sexo.short} · ${patient.ageAt(now)} · Fototipo ${patient.fototipo.roman}',
                        style: const TextStyle(fontSize: 13, color: AppColors.textSubtle),
                      ),
                    ],
                  ),
                ),
              const SizedBox(height: 12),
              PredictionCard(prediction: p),
              if (c.suggestion != null) ...[
                const SizedBox(height: 12),
                Container(
                  padding: const EdgeInsets.fromLTRB(14, 12, 6, 12),
                  decoration: BoxDecoration(
                      color: AppColors.warningBg, borderRadius: BorderRadius.circular(14)),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text('Sugerencia · ${p.riskLabel.toLowerCase()}',
                                style: const TextStyle(
                                    fontWeight: FontWeight.w700,
                                    fontSize: 13,
                                    color: Color(0xFF4A3405))),
                          ),
                          TextButton(
                            onPressed: () => _editSuggestion(context, ref),
                            style: TextButton.styleFrom(
                                visualDensity: VisualDensity.compact,
                                padding: const EdgeInsets.symmetric(horizontal: 8)),
                            child: const Text('Editar'),
                          ),
                        ],
                      ),
                      Padding(
                        padding: const EdgeInsets.only(right: 8),
                        child: Text(c.suggestion!,
                            style: const TextStyle(
                                fontSize: 13, height: 1.45, color: Color(0xFF4A3405))),
                      ),
                    ],
                  ),
                ),
              ],
              const SizedBox(height: 12),
              AppCard(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                child: Column(
                  children: [
                    KeyValueRow('Ubicación', c.clinicalData.ubicacionLesion),
                    KeyValueRow('Aparición', c.clinicalData.tiempoAparicion.label),
                    KeyValueRow('Síntomas', c.clinicalData.sintomasLabel),
                    if (c.foto2.source != null)
                      KeyValueRow('Captura',
                          c.foto2.source == CaptureSource.camara ? 'Cámara' : 'Galería'),
                    KeyValueRow('Registrado', Fmt.dateTime(c.createdAt), mono: true),
                  ],
                ),
              ),
            ],
          ),
        ),
        Container(
          padding: const EdgeInsets.fromLTRB(18, 12, 18, 18),
          decoration: const BoxDecoration(
            color: Colors.white,
            border: Border(top: BorderSide(color: AppColors.divider)),
          ),
          child: SafeArea(
            top: false,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                PrimaryButton(
                  label: 'Validar predicción',
                  onPressed: () => context.push('/caso/${c.id}/validar'),
                ),
                const SizedBox(height: 8),
                const Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(Icons.lock_outline, size: 14, color: AppColors.textDisabled),
                    SizedBox(width: 6),
                    Text('Cerrar y exportar requiere validación',
                        style: TextStyle(fontSize: 12, color: AppColors.textDisabled)),
                  ],
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// Predicción preliminar etiquetada como no validada (RF-03.3).
class PredictionCard extends StatelessWidget {
  const PredictionCard({super.key, required this.prediction});
  final Prediction prediction;

  @override
  Widget build(BuildContext context) {
    final p = prediction;
    final barColor = switch (p.confidence) {
      PredictionConfidence.alta => AppColors.error,
      PredictionConfidence.ambigua || PredictionConfidence.baja => AppColors.warningAccent,
      PredictionConfidence.benigna => AppColors.primary,
    };
    final riskColor = switch (p.confidence) {
      PredictionConfidence.alta => AppColors.errorText,
      PredictionConfidence.ambigua || PredictionConfidence.baja => AppColors.warningText,
      PredictionConfidence.benigna => AppColors.primaryDark,
    };
    return DashedBorderBox(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SectionLabel('PREDICCIÓN PRELIMINAR · NO VALIDADA',
              color: AppColors.warningText),
          const SizedBox(height: 10),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Expanded(
                child: Text(p.headline,
                    style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  const Text('Riesgo estimado',
                      style: TextStyle(fontSize: 11, color: AppColors.textSubtle)),
                  Text('${p.percent}%',
                      style: AppFonts.mono(fontSize: 20, color: AppColors.text)),
                ],
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(p.riskLabel,
              style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: riskColor)),
          const SizedBox(height: 12),
          LayoutBuilder(builder: (context, box) {
            final w = box.maxWidth;
            return SizedBox(
              height: 16,
              child: Stack(
                clipBehavior: Clip.none,
                alignment: Alignment.centerLeft,
                children: [
                  Container(
                    height: 8,
                    decoration: BoxDecoration(
                        color: AppColors.divider, borderRadius: BorderRadius.circular(4)),
                  ),
                  Container(
                    height: 8,
                    width: w * p.probabilidadMalignidad.clamp(0.02, 1.0),
                    decoration:
                        BoxDecoration(color: barColor, borderRadius: BorderRadius.circular(4)),
                  ),
                  Positioned(
                    left: (w * p.umbralOperativo - 1).clamp(0, w - 2),
                    child: Container(
                      width: 2,
                      height: 16,
                      decoration: BoxDecoration(
                          color: AppColors.text, borderRadius: BorderRadius.circular(1)),
                    ),
                  ),
                ],
              ),
            );
          }),
          const SizedBox(height: 6),
          Row(
            children: [
              const Expanded(
                child: Text('0%', style: TextStyle(fontSize: 11, color: AppColors.textSubtle)),
              ),
              Text('▲ Alerta desde ${p.alertPercent}%',
                  style: const TextStyle(
                      fontSize: 11, fontWeight: FontWeight.w600, color: AppColors.textMuted)),
              const Expanded(
                child: Text('100%',
                    textAlign: TextAlign.end,
                    style: TextStyle(fontSize: 11, color: AppColors.textSubtle)),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(p.frequencyText,
              style: const TextStyle(fontSize: 13, height: 1.4, color: AppColors.textBody)),
          const SizedBox(height: 4),
          Text(
            'El sistema avisa desde un ${p.alertPercent}% de riesgo para no pasar por alto '
            'melanomas; por eso muchas alertas resultan benignas.',
            style: const TextStyle(fontSize: 13, height: 1.4, color: AppColors.textMuted),
          ),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: () => _showHowToRead(context, p),
              style: TextButton.styleFrom(
                  visualDensity: VisualDensity.compact,
                  padding: const EdgeInsets.symmetric(horizontal: 4)),
              icon: const Icon(Icons.help_outline, size: 16),
              label: const Text('¿Cómo leer este resultado?'),
            ),
          ),
        ],
      ),
    );
  }

  static void _showHowToRead(BuildContext context, Prediction p) {
    Widget section(String title, String body) => Padding(
          padding: const EdgeInsets.only(bottom: 16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
              const SizedBox(height: 4),
              Text(body,
                  style: const TextStyle(fontSize: 14, height: 1.45, color: AppColors.textBody)),
            ],
          ),
        );
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (ctx) => SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(20, 20, 20, 12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Cómo leer este resultado',
                  style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
              const SizedBox(height: 16),
              section(
                'Riesgo estimado: ${p.percent}%',
                'Es la proporción de lesiones con fotos parecidas a estas que resultaron '
                    'ser melanoma. ${p.frequencyText}',
              ),
              section(
                'Línea de alerta: ${p.alertPercent}%',
                'Desde ese riesgo, el sistema marca la lesión como posible melanoma. '
                    'Es baja a propósito: es preferible revisar una lesión benigna de más '
                    'que dejar pasar un melanoma.',
              ),
              section(
                'Qué esperar de las alertas',
                'Como la línea de alerta es baja, el sistema detecta la gran mayoría de los '
                    'melanomas, pero también marca muchas lesiones que resultan benignas. '
                    'Una alerta indica que la lesión merece su revisión, no que sea maligna.',
              ),
              section(
                'La decisión es suya',
                'El resultado no es un diagnóstico. Confírmelo o corríjalo con su criterio '
                    'clínico y los exámenes que considere necesarios.',
              ),
              Text('Modelo ${p.versionModelo}',
                  style: const TextStyle(fontSize: 12, color: AppColors.textSubtle)),
            ],
          ),
        ),
      ),
    );
  }
}
