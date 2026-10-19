import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/utils/formatters.dart';
import '../../core/widgets/common.dart';
import '../../domain/models/patient.dart';
import '../../providers/repository_providers.dart';
import '../auth/auth_widgets.dart';

/// Pantalla 08 · Registrar paciente sin credenciales (HU06·CA1, RF-02.5).
class RegisterPatientScreen extends ConsumerStatefulWidget {
  const RegisterPatientScreen({super.key, this.initialHc});
  final String? initialHc;

  @override
  ConsumerState<RegisterPatientScreen> createState() => _RegisterPatientScreenState();
}

class _RegisterPatientScreenState extends ConsumerState<RegisterPatientScreen> {
  final _formKey = GlobalKey<FormState>();
  late final _hc = TextEditingController(text: widget.initialHc ?? '');
  final _names = TextEditingController();
  final _birthText = TextEditingController();
  DateTime? _birth;
  Sex _sex = Sex.femenino;
  Phototype? _phototype;
  bool _saving = false;
  bool _attempted = false;

  @override
  void dispose() {
    _hc.dispose();
    _names.dispose();
    _birthText.dispose();
    super.dispose();
  }

  Future<void> _pickBirth() async {
    final now = ref.read(clockProvider)();
    final picked = await showDatePicker(
      context: context,
      initialDate: _birth ?? DateTime(now.year - 50),
      firstDate: DateTime(1900),
      lastDate: now,
      helpText: 'Fecha de nacimiento',
    );
    if (picked != null) {
      setState(() {
        _birth = picked;
        _birthText.text = Fmt.date(picked);
      });
    }
  }

  Future<void> _submit() async {
    setState(() => _attempted = true);
    if (!_formKey.currentState!.validate() || _birth == null || _phototype == null) return;
    setState(() => _saving = true);
    try {
      final patient = await ref.read(patientRepositoryProvider).registerPatient(
            numeroHistoriaClinica: _hc.text,
            nombres: _names.text,
            fechaNacimiento: _birth!,
            sexo: _sex,
            fototipo: _phototype!,
          );
      if (!mounted) return;
      context.pushReplacement('/paciente/${patient.id}/consentimiento');
    } on AppException catch (e) {
      if (mounted) showAppSnack(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    String? required(String? v) =>
        (v == null || v.trim().isEmpty) ? 'Campo obligatorio' : null;

    return Scaffold(
      appBar: AppBar(title: const Text('Paciente nuevo')),
      body: SafeArea(
        top: false,
        child: Form(
          key: _formKey,
          child: BottomPinnedScroll(
            padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
            children: [
              AppTextField(
                label: 'N.° de historia clínica',
                controller: _hc,
                mono: true,
                hint: 'HC-000000',
                textCapitalization: TextCapitalization.characters,
                validator: required,
              ),
              const SizedBox(height: 14),
              AppTextField(
                label: 'Nombres y apellidos',
                controller: _names,
                textCapitalization: TextCapitalization.words,
                validator: required,
              ),
              const SizedBox(height: 14),
              AppTextField(
                label: 'Fecha de nacimiento',
                controller: _birthText,
                readOnly: true,
                onTap: _pickBirth,
                hint: 'dd/mm/aaaa',
                suffix: const Icon(Icons.calendar_today_outlined, size: 18),
                errorText: _attempted && _birth == null ? 'Selecciona la fecha' : null,
              ),
              const SizedBox(height: 14),
              const FieldLabel('Sexo'),
              SegmentedSelector<Sex>(
                options: Sex.values,
                selected: _sex,
                labelOf: (s) => s.label,
                onChanged: (s) => setState(() => _sex = s),
              ),
              const SizedBox(height: 16),
              FieldLabel('Fototipo de piel (Fitzpatrick)',
                  error: _attempted && _phototype == null),
              Row(
                children: [
                  for (final ph in Phototype.values)
                    Expanded(
                      child: Padding(
                        padding: EdgeInsets.only(right: ph == Phototype.vi ? 0 : 6),
                        child: GestureDetector(
                          onTap: () => setState(() => _phototype = ph),
                          child: Container(
                            height: 44,
                            alignment: Alignment.center,
                            decoration: BoxDecoration(
                              color: AppColors.phototypes[ph.index],
                              borderRadius: BorderRadius.circular(10),
                              border: _phototype == ph
                                  ? Border.all(color: AppColors.primary, width: 2.5)
                                  : null,
                            ),
                            child: Text(ph.roman,
                                style: TextStyle(
                                  fontWeight: FontWeight.w600,
                                  color: ph.index >= 3 ? Colors.white : AppColors.text,
                                )),
                          ),
                        ),
                      ),
                    ),
                ],
              ),
              if (_attempted && _phototype == null)
                const Padding(
                  padding: EdgeInsets.only(top: 6),
                  child: Text('Selecciona el fototipo',
                      style: TextStyle(color: AppColors.error, fontSize: 12)),
                ),
            ],
            bottom: [
              const Text('No se generarán credenciales para el paciente.',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 12, color: AppColors.textSubtle)),
              const SizedBox(height: 10),
              PrimaryButton(label: 'Registrar y continuar', loading: _saving, onPressed: _submit),
            ],
          ),
        ),
      ),
    );
  }
}
