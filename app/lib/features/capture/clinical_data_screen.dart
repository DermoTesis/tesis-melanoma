import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/widgets/common.dart';
import '../../domain/models/clinical_case.dart';
import '../../providers/case_providers.dart';
import '../../providers/repository_providers.dart';

const kBodySites = [
  'Cuero cabelludo',
  'Frente',
  'Mejilla derecha',
  'Mejilla izquierda',
  'Nariz',
  'Cuello',
  'Tórax anterior',
  'Abdomen',
  'Espalda, región escapular derecha',
  'Espalda, región escapular izquierda',
  'Espalda, región lumbar',
  'Brazo derecho',
  'Brazo izquierdo',
  'Antebrazo derecho, cara dorsal',
  'Antebrazo izquierdo, cara dorsal',
  'Mano derecha',
  'Mano izquierda',
  'Muslo derecho',
  'Muslo izquierdo',
  'Pierna derecha, cara anterior',
  'Pierna izquierda, cara anterior',
  'Planta del pie derecho',
  'Planta del pie izquierdo',
  'Región subungueal',
  'Otra ubicación',
];

/// Pantalla 13 · Datos clínicos complementarios (HU11, RF-02.3) y envío (HU12).
class ClinicalDataScreen extends ConsumerStatefulWidget {
  const ClinicalDataScreen({super.key, required this.patientId});
  final String patientId;

  @override
  ConsumerState<ClinicalDataScreen> createState() => _ClinicalDataScreenState();
}

class _ClinicalDataScreenState extends ConsumerState<ClinicalDataScreen> {
  String? _site;
  final _otherSite = TextEditingController();
  OnsetTime? _onset;
  final _symptoms = <Symptom>{};
  bool _attempted = false;
  bool _sending = false;

  @override
  void dispose() {
    _otherSite.dispose();
    super.dispose();
  }

  String get _siteValue => _site == 'Otra ubicación' ? _otherSite.text.trim() : (_site ?? '');

  Future<void> _send() async {
    setState(() => _attempted = true);
    final draft = ref.read(captureDraftProvider);
    if (draft == null || !draft.hasBothImages) {
      showAppSnack(context, 'Faltan imágenes aptas del caso.', error: true);
      return;
    }
    if (_siteValue.isEmpty || _onset == null) return;
    setState(() => _sending = true);
    try {
      final c = await ref
          .read(caseRepositoryProvider)
          .submitCase(
            draft,
            ClinicalData(
              ubicacionLesion: _siteValue,
              tiempoAparicion: _onset!,
              sintomas: Set.of(_symptoms),
            ),
          );
      ref.read(captureDraftProvider.notifier).reset();
      if (mounted) context.go('/caso/${c.id}/enviado');
    } on AppException catch (e) {
      if (mounted) showAppSnack(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final draft = ref.watch(captureDraftProvider);
    final siteError = _attempted && _siteValue.isEmpty;
    final onsetError = _attempted && _onset == null;

    return Scaffold(
      appBar: AppBar(title: const Text('Datos de la lesión')),
      body: SafeArea(
        top: false,
        child: Column(
          children: [
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(20, 4, 20, 16),
                children: [
                  const StepProgress(total: 4, current: 3),
                  const SizedBox(height: 14),
                  AppCard(
                    padding: const EdgeInsets.all(10),
                    child: Row(
                      children: [
                        LesionThumbnail(path: draft?.foto1?.localPath, size: 52),
                        const SizedBox(width: 6),
                        LesionThumbnail(path: draft?.foto2?.localPath, size: 52, dark: true),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                '${[draft?.foto1, draft?.foto2].where((e) => e != null).length} de 2 imágenes aptas',
                                style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
                              ),
                              Text(
                                'Fotos dermatoscópicas de la misma lesión',
                                style: const TextStyle(fontSize: 12, color: AppColors.primaryDark),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),
                  FieldLabel('Ubicación corporal *', error: siteError),
                  DropdownButtonFormField<String>(
                    initialValue: _site,
                    isExpanded: true,
                    hint: const Text('Selecciona la ubicación'),
                    decoration: InputDecoration(
                      errorText: siteError && _site == null ? 'Selecciona la ubicación' : null,
                    ),
                    items: [for (final s in kBodySites) DropdownMenuItem(value: s, child: Text(s))],
                    onChanged: (v) => setState(() => _site = v),
                  ),
                  if (_site == 'Otra ubicación') ...[
                    const SizedBox(height: 10),
                    AppTextField(
                      label: 'Describe la ubicación',
                      controller: _otherSite,
                      onChanged: (_) => setState(() {}),
                      errorText: siteError ? 'Describe la ubicación' : null,
                    ),
                  ],
                  if (siteNoticeFor(_siteValue) case final notice?) ...[
                    const SizedBox(height: 10),
                    InfoBanner(tone: BannerTone.warning, message: notice),
                  ],
                  const SizedBox(height: 16),
                  FieldLabel('Tiempo de aparición *', error: onsetError),
                  Container(
                    padding: onsetError ? const EdgeInsets.all(8) : EdgeInsets.zero,
                    decoration: onsetError
                        ? BoxDecoration(
                            color: AppColors.errorSurface,
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(color: AppColors.errorBorder, width: 1.5),
                          )
                        : null,
                    child: Wrap(
                      spacing: 6,
                      runSpacing: 6,
                      children: [
                        for (final o in OnsetTime.values)
                          PillChip(
                            label: o.label,
                            selected: _onset == o,
                            outlined: !onsetError,
                            onTap: () => setState(() => _onset = o),
                          ),
                      ],
                    ),
                  ),
                  if (onsetError)
                    const Padding(
                      padding: EdgeInsets.only(top: 6),
                      child: Text(
                        'Selecciona una opción para enviar el caso.',
                        style: TextStyle(fontSize: 12, color: AppColors.error),
                      ),
                    ),
                  const SizedBox(height: 16),
                  const FieldLabel('Síntomas referidos'),
                  Wrap(
                    spacing: 6,
                    runSpacing: 6,
                    children: [
                      for (final s in Symptom.values)
                        PillChip(
                          label: s.label,
                          selected: _symptoms.contains(s),
                          onTap: () => setState(() {
                            _symptoms.contains(s) ? _symptoms.remove(s) : _symptoms.add(s);
                          }),
                        ),
                    ],
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
              child: PrimaryButton(label: 'Enviar a análisis', loading: _sending, onPressed: _send),
            ),
          ],
        ),
      ),
    );
  }
}
