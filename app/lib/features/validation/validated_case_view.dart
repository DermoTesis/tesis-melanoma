import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../core/widgets/common.dart';
import '../../domain/models/clinical_case.dart';
import '../../domain/models/validation.dart';
import '../../providers/repository_providers.dart';

/// Pantalla 18 · Caso validado: registro inmutable, conducta clínica y
/// observaciones internas (HU23, HU26, HU31, RF-04.4, RF-05.4, RF-06.3).
class ValidatedCaseView extends ConsumerStatefulWidget {
  const ValidatedCaseView({super.key, required this.clinicalCase});
  final ClinicalCase clinicalCase;

  @override
  ConsumerState<ValidatedCaseView> createState() => _ValidatedCaseViewState();
}

class _ValidatedCaseViewState extends ConsumerState<ValidatedCaseView> {
  final _conducta = TextEditingController();
  final _note = TextEditingController();
  bool _closing = false;
  bool _addingNote = false;
  bool _attempted = false;

  @override
  void dispose() {
    _conducta.dispose();
    _note.dispose();
    super.dispose();
  }

  Future<void> _close() async {
    setState(() => _attempted = true);
    if (_conducta.text.trim().isEmpty) return;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cerrar caso'),
        content: const Text(
            'Se cerrará el caso y se generará el informe con la conclusión validada. '
            'Las observaciones internas no se incluyen en el informe.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
          TextButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Cerrar caso')),
        ],
      ),
    );
    if (ok != true) return;
    setState(() => _closing = true);
    try {
      await ref.read(reportRepositoryProvider).closeCase(widget.clinicalCase.id, _conducta.text);
      if (mounted) context.push('/caso/${widget.clinicalCase.id}/informe');
    } on AppException catch (e) {
      if (mounted) showAppSnack(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _closing = false);
    }
  }

  Future<void> _addNote() async {
    if (_note.text.trim().isEmpty) return;
    setState(() => _addingNote = true);
    try {
      await ref.read(caseRepositoryProvider).addInternalNote(widget.clinicalCase.id, _note.text);
      _note.clear();
    } on AppException catch (e) {
      if (mounted) showAppSnack(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _addingNote = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.clinicalCase;
    final validations =
        ref.watch(validationsProvider(c.id)).value ?? const <ClinicalValidation>[];
    final report = ref.watch(reportProvider(c.id)).value;
    final closed = c.status == CaseStatus.cerrado;

    return Column(
      children: [
        Expanded(
          child: ListView(
            padding: const EdgeInsets.fromLTRB(18, 0, 18, 18),
            children: [
              for (final v in validations) ...[
                _ValidationRecord(validation: v),
                const SizedBox(height: 10),
              ],
              if (validations.isNotEmpty)
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton.icon(
                    onPressed: () =>
                        context.push('/caso/${c.id}/validar?complementa=${validations.first.id}'),
                    icon: const Icon(Icons.add, size: 18),
                    label: const Text('Validación complementaria'),
                  ),
                ),
              const SizedBox(height: 6),
              if (closed && report != null) ...[
                const FieldLabel('Conducta / recomendación clínica'),
                AppCard(
                  padding: const EdgeInsets.all(12),
                  child: Text(report.conductaClinica,
                      style: const TextStyle(fontSize: 14, height: 1.45)),
                ),
                const SizedBox(height: 6),
                Text('Caso cerrado el ${Fmt.dateTime(report.fechaCierre)}',
                    style: const TextStyle(fontSize: 12, color: AppColors.textSubtle)),
              ] else ...[
                AppTextField(
                  label: 'Conducta / recomendación clínica *',
                  controller: _conducta,
                  maxLines: 4,
                  minLines: 2,
                  hint: 'p. ej., biopsia excisional, control dermatoscópico…',
                  onChanged: (_) {
                    if (_attempted) setState(() {});
                  },
                  errorText: _attempted && _conducta.text.trim().isEmpty
                      ? 'Registra la conducta para cerrar el caso.'
                      : null,
                ),
                const SizedBox(height: 6),
                const Text('Se incluye en el informe. La app no agenda citas ni derivaciones.',
                    style: TextStyle(fontSize: 11, color: AppColors.textSubtle)),
              ],
              const SizedBox(height: 18),
              const Row(
                children: [
                  Expanded(child: FieldLabel('Observaciones internas')),
                  Padding(
                    padding: EdgeInsets.only(bottom: 6),
                    child: StatusChip('NO SE EXPORTA'),
                  ),
                ],
              ),
              for (final n in c.internalNotes)
                Container(
                  margin: const EdgeInsets.only(bottom: 8),
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                      color: AppColors.surfaceMuted, borderRadius: BorderRadius.circular(12)),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(n.text,
                          style: const TextStyle(
                              fontSize: 13, height: 1.45, color: AppColors.textBody)),
                      const SizedBox(height: 4),
                      Text('${n.authorName} · ${Fmt.dateTime(n.createdAt)}',
                          style: AppFonts.mono(fontSize: 10)),
                    ],
                  ),
                ),
              Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Expanded(
                    child: TextField(
                      controller: _note,
                      minLines: 1,
                      maxLines: 3,
                      decoration: const InputDecoration(
                        hintText: 'Agregar observación interna',
                        fillColor: AppColors.surfaceMuted,
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  IconButton.filled(
                    style: IconButton.styleFrom(backgroundColor: AppColors.primary),
                    onPressed: _addingNote ? null : _addNote,
                    icon: const Icon(Icons.send, size: 18),
                  ),
                ],
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
            child: closed
                ? PrimaryButton(
                    label: 'Ver informe PDF',
                    icon: Icons.picture_as_pdf_outlined,
                    onPressed: () => context.push('/caso/${c.id}/informe'),
                  )
                : PrimaryButton(
                    label: 'Cerrar caso y generar informe',
                    loading: _closing,
                    onPressed: _close,
                  ),
          ),
        ),
      ],
    );
  }
}

class _ValidationRecord extends StatelessWidget {
  const _ValidationRecord({required this.validation});
  final ClinicalValidation validation;

  @override
  Widget build(BuildContext context) {
    final v = validation;
    final p = v.prediccionOriginal;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
          color: AppColors.successBg, borderRadius: BorderRadius.circular(16)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: SectionLabel(
                  v.isComplementary
                      ? 'VALIDACIÓN COMPLEMENTARIA · INMUTABLE'
                      : 'VALIDACIÓN · REGISTRO INMUTABLE',
                  color: AppColors.primaryDark,
                ),
              ),
              const Icon(Icons.lock, size: 14, color: AppColors.primaryDark),
            ],
          ),
          const SizedBox(height: 8),
          Text(v.conclusionLabel,
              style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          _Line('Especialista', '${v.especialistaNombre} · CMP ${v.cmp}'),
          _Line('Fecha', Fmt.dateTimeSeconds(v.fechaValidacion), mono: true),
          _Line('Modelo', '${p.shortSummary} (${p.versionModelo})'),
          _Line('Sustento', v.sustentoClinico),
          if (v.sugerenciaTomada != null)
            _Line('Sugerencia', v.sugerenciaTomada! ? 'Tomada' : 'No tomada'),
          if (v.claseFinal != null && v.claseFinal != p.clasePredicha)
            const Padding(
              padding: EdgeInsets.only(top: 4),
              child: Text('La predicción original se conserva sin cambios.',
                  style: TextStyle(fontSize: 11, color: AppColors.primaryDark)),
            ),
        ],
      ),
    );
  }
}

class _Line extends StatelessWidget {
  const _Line(this.label, this.value, {this.mono = false});
  final String label;
  final String value;
  final bool mono;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 86,
            child: Text(label, style: const TextStyle(fontSize: 12, color: Color(0xFF4D6B5C))),
          ),
          Expanded(
            child: Text(value,
                style: mono
                    ? AppFonts.mono(fontSize: 12, color: AppColors.textBody)
                    : const TextStyle(fontSize: 12, color: AppColors.textBody, height: 1.35)),
          ),
        ],
      ),
    );
  }
}
