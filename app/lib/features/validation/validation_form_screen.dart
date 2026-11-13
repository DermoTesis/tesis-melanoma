import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/widgets/common.dart';
import '../../domain/models/clinical_case.dart';
import '../../domain/models/prediction.dart';
import '../../domain/models/validation.dart';
import '../../providers/repository_providers.dart';

/// Pantalla 17 · Registrar validación (HU21, HU22, HU29·CA2, RF-04.2, RF-04.3).
class ValidationFormScreen extends ConsumerStatefulWidget {
  const ValidationFormScreen({super.key, required this.caseId, this.complementaDe});
  final String caseId;

  /// Si se indica, se registra una validación complementaria.
  final String? complementaDe;

  @override
  ConsumerState<ValidationFormScreen> createState() => _ValidationFormScreenState();
}

class _ValidationFormScreenState extends ConsumerState<ValidationFormScreen> {
  ValidationDecision _decision = ValidationDecision.confirmar;
  LesionClass? _correctedClass;
  final _sustento = TextEditingController();
  bool? _suggestionTaken;
  bool _attempted = false;
  bool _saving = false;

  @override
  void dispose() {
    _sustento.dispose();
    super.dispose();
  }

  Future<void> _save(ClinicalCase c) async {
    setState(() => _attempted = true);
    final p = c.prediction!;
    if (_sustento.text.trim().isEmpty) return;
    if (_decision == ValidationDecision.corregir && _correctedClass == null) return;
    if (c.suggestion != null && _suggestionTaken == null) return;
    setState(() => _saving = true);
    try {
      await ref.read(validationRepositoryProvider).registerValidation(
            caseId: c.id,
            decision: _decision,
            sustentoClinico: _sustento.text,
            claseFinal: _decision == ValidationDecision.confirmar ? p.clasePredicha : _correctedClass,
            examenesAdicionales: c.suggestion,
            sugerenciaTomada: c.suggestion == null ? null : _suggestionTaken,
            complementaDe: widget.complementaDe,
          );
      if (!mounted) return;
      showAppSnack(context, 'Validación registrada de forma inmutable.');
      context.pop();
    } on AppException catch (e) {
      if (mounted) showAppSnack(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final caseAsync = ref.watch(caseProvider(widget.caseId));
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(icon: const Icon(Icons.close), onPressed: () => context.pop()),
        title: Text(widget.complementaDe == null
            ? 'Validación · ${widget.caseId}'
            : 'Complementaria · ${widget.caseId}'),
      ),
      body: caseAsync.when(
        loading: () => const LoadingView(),
        error: (e, _) => ErrorView('$e'),
        data: (c) {
          if (c == null) return const ErrorView('Caso no encontrado.');
          final p = c.prediction;
          if (p == null) {
            return const ErrorView(
                'La validación no está disponible hasta que termine la predicción preliminar.');
          }
          final sustentoError = _attempted && _sustento.text.trim().isEmpty;
          final other = p.clasePredicha == LesionClass.maligno
              ? LesionClass.benigno
              : LesionClass.maligno;

          return SafeArea(
            top: false,
            child: Column(
              children: [
                Expanded(
                  child: ListView(
                    padding: const EdgeInsets.fromLTRB(18, 4, 18, 18),
                    children: [
                      AppCard(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                        child: KeyValueRow('Predicción original',
                            p.shortSummary, bold: true),
                      ),
                      if (widget.complementaDe != null) ...[
                        const SizedBox(height: 12),
                        const InfoBanner(
                          message:
                              'La validación original no se modifica. Esta validación complementaria se añadirá al registro.',
                        ),
                      ],
                      const SizedBox(height: 16),
                      const FieldLabel('Tu decisión'),
                      SegmentedSelector<ValidationDecision>(
                        options: ValidationDecision.values,
                        selected: _decision,
                        solidSelection: true,
                        labelOf: (d) => d.label,
                        onChanged: (d) => setState(() {
                          _decision = d;
                          _correctedClass = d == ValidationDecision.corregir ? other : null;
                        }),
                      ),
                      const SizedBox(height: 16),
                      if (_decision != ValidationDecision.descartar) ...[
                        const FieldLabel('Clasificación del especialista'),
                        Row(
                          children: [
                            for (final cls in LesionClass.values) ...[
                              Expanded(
                                child: _ClassOption(
                                  label: cls.label,
                                  selected: _decision == ValidationDecision.confirmar
                                      ? cls == p.clasePredicha
                                      : cls == _correctedClass,
                                  enabled: _decision == ValidationDecision.corregir &&
                                      cls != p.clasePredicha,
                                  onTap: () => setState(() => _correctedClass = cls),
                                ),
                              ),
                              if (cls == LesionClass.benigno) const SizedBox(width: 8),
                            ],
                          ],
                        ),
                        const SizedBox(height: 16),
                      ] else ...[
                        const InfoBanner(
                          tone: BannerTone.warning,
                          message:
                              'Al descartar, el informe indicará que la predicción preliminar no es concluyente y que se requiere evaluación clínica.',
                        ),
                        const SizedBox(height: 16),
                      ],
                      AppTextField(
                        label: 'Sustento clínico *',
                        controller: _sustento,
                        maxLines: 5,
                        minLines: 3,
                        hint: 'Describe los hallazgos que justifican tu decisión…',
                        onChanged: (_) {
                          if (_attempted) setState(() {});
                        },
                        errorText: sustentoError
                            ? 'El sustento clínico es obligatorio para guardar la validación.'
                            : null,
                      ),
                      if (c.suggestion != null) ...[
                        const SizedBox(height: 14),
                        AppCard(
                          padding: const EdgeInsets.all(12),
                          border: _attempted && _suggestionTaken == null
                              ? Border.all(color: AppColors.errorBorder, width: 1.5)
                              : null,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text('Sugerencia de exámenes adicionales',
                                  style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
                              const SizedBox(height: 4),
                              Text(c.suggestion!,
                                  style: const TextStyle(
                                      fontSize: 12, color: AppColors.textSubtle, height: 1.4)),
                              RadioGroup<bool>(
                                groupValue: _suggestionTaken,
                                onChanged: (v) => setState(() => _suggestionTaken = v),
                                child: const Row(
                                  children: [
                                    Radio<bool>(value: true),
                                    Text('Tomada', style: TextStyle(fontSize: 13)),
                                    SizedBox(width: 12),
                                    Radio<bool>(value: false),
                                    Text('No tomada', style: TextStyle(fontSize: 13)),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.fromLTRB(18, 0, 18, 18),
                  child: Column(
                    children: [
                      const Text('La predicción original se conserva sin sobrescribirse.',
                          style: TextStyle(fontSize: 12, color: AppColors.textSubtle)),
                      const SizedBox(height: 8),
                      PrimaryButton(
                        label: 'Guardar validación',
                        loading: _saving,
                        onPressed: () => _save(c),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _ClassOption extends StatelessWidget {
  const _ClassOption({
    required this.label,
    required this.selected,
    required this.enabled,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: enabled ? onTap : null,
      child: Container(
        height: 46,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: selected ? AppColors.primary : AppColors.border,
            width: selected ? 2 : 1.5,
          ),
        ),
        child: Text(label,
            style: TextStyle(
              fontSize: 15,
              fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
              color: selected ? AppColors.text : AppColors.textSubtle,
            )),
      ),
    );
  }
}
