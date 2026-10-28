import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/common.dart';
import '../../domain/models/clinical_case.dart';
import '../../domain/models/patient.dart';
import '../../providers/repository_providers.dart';
import 'patient_widgets.dart';

/// Pantalla 07 · Buscar paciente por número de historia clínica (HU06·CA2).
class PatientSearchScreen extends ConsumerStatefulWidget {
  const PatientSearchScreen({super.key});

  @override
  ConsumerState<PatientSearchScreen> createState() => _PatientSearchScreenState();
}

class _PatientSearchScreenState extends ConsumerState<PatientSearchScreen> {
  final _hc = TextEditingController();
  bool _searching = false;
  bool _searched = false;
  Patient? _result;

  @override
  void dispose() {
    _hc.dispose();
    super.dispose();
  }

  void _select(Patient p) {
    FocusScope.of(context).unfocus();
    _hc.text = p.numeroHistoriaClinica;
    setState(() {
      _result = p;
      _searched = true;
    });
  }

  Future<void> _search() async {
    if (_hc.text.trim().isEmpty) return;
    FocusScope.of(context).unfocus();
    setState(() => _searching = true);
    try {
      final p = await ref.read(patientRepositoryProvider).findByHistoriaClinica(_hc.text);
      if (!mounted) return;
      setState(() {
        _result = p;
        _searched = true;
      });
    } on AppException catch (e) {
      if (mounted) showAppSnack(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _searching = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final now = ref.watch(clockProvider)();
    final result = _result;
    // Se observa el paciente para reflejar cambios de consentimiento.
    final live = result == null ? null : ref.watch(patientProvider(result.id)).value;
    final patient = live ?? result;
    final previous = patient == null
        ? 0
        : (ref.watch(patientCasesProvider(patient.id)).value ?? const <ClinicalCase>[]).length;
    // Sugerencias en vivo: historias clínicas (o nombres) que contienen lo escrito.
    final query = _hc.text.trim().toLowerCase();
    final suggestions = query.isEmpty
        ? const <Patient>[]
        : (ref.watch(patientsProvider).value ?? const <Patient>[])
            .where((p) =>
                p.numeroHistoriaClinica.toLowerCase().contains(query) ||
                p.nombres.toLowerCase().contains(query))
            .take(6)
            .toList();

    return Scaffold(
      appBar: AppBar(title: const Text('Nuevo caso')),
      body: SafeArea(
        top: false,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
          children: [
            const StepProgress(total: 4, current: 1),
            const SizedBox(height: 18),
            const Text('¿A quién atiendes?',
                style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
            const SizedBox(height: 16),
            AppTextField(
              label: 'N.° de historia clínica o Nombre del Paciente',
              controller: _hc,
              mono: true,
              hint: 'HC-000000',
              textCapitalization: TextCapitalization.characters,
              onChanged: (_) => setState(() => _searched = false),
              suffix: IconButton(
                onPressed: _searching ? null : _search,
                icon: _searching
                    ? const SizedBox(
                        width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.search, color: AppColors.primary),
              ),
            ),
            if (!_searched && query.isNotEmpty) ...[
              const SizedBox(height: 8),
              if (suggestions.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 4, vertical: 6),
                  child: Text('Sin coincidencias',
                      style: TextStyle(fontSize: 13, color: AppColors.textSubtle)),
                )
              else
                for (final p in suggestions) ...[
                  AppCard(
                    padding: const EdgeInsets.all(14),
                    onTap: () => _select(p),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        PatientHeader(patient: p, now: now),
                        const SizedBox(height: 10),
                        Row(
                          children: [
                            Text(p.numeroHistoriaClinica, style: AppFonts.mono(fontSize: 12)),
                            const Spacer(),
                            ConsentChip(patient: p),
                          ],
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 8),
                ],
            ],
            const SizedBox(height: 12),
            PrimaryButton(label: 'Buscar', loading: _searching, onPressed: _search),
            const SizedBox(height: 18),
            if (_searched && patient != null) ...[
              AppCard(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Row(
                      children: [
                        CircleAvatar(radius: 4, backgroundColor: AppColors.primary),
                        SizedBox(width: 8),
                        Text('Expediente existente',
                            style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                                color: AppColors.primaryDark)),
                      ],
                    ),
                    const SizedBox(height: 12),
                    PatientHeader(patient: patient, now: now),
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 8,
                      runSpacing: 6,
                      children: [
                        ConsentChip(patient: patient),
                        StatusChip('$previous caso${previous == 1 ? '' : 's'} previo${previous == 1 ? '' : 's'}'),
                      ],
                    ),
                    const SizedBox(height: 14),
                    SizedBox(
                      height: 46,
                      child: FilledButton(
                        style: FilledButton.styleFrom(
                          minimumSize: const Size.fromHeight(46),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                        ),
                        onPressed: () => startCaseFor(context, ref, patient),
                        child: Text(patient.sexo == Sex.femenino
                            ? 'Iniciar caso para esta paciente'
                            : 'Iniciar caso para este paciente'),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              const Text(
                'El número de historia clínica ya existe: se muestra el expediente sin crear un duplicado.',
                style: TextStyle(fontSize: 13, color: AppColors.textSubtle, height: 1.45),
              ),
            ],
            if (_searched && patient == null)
              InfoBanner(
                tone: BannerTone.warning,
                title: 'Sin expediente',
                message:
                    'No existe un paciente con la historia clínica ${_hc.text.trim().toUpperCase()}. Regístralo para continuar.',
              ),
            const SizedBox(height: 24),
            OutlinedButton.icon(
              style: OutlinedButton.styleFrom(
                foregroundColor: AppColors.primary,
                side: const BorderSide(color: AppColors.borderDashed, width: 1.5),
                minimumSize: const Size.fromHeight(52),
              ),
              onPressed: () {
                final hc = Uri.encodeQueryComponent(_hc.text.trim().toUpperCase());
                context.push('/paciente/nuevo${hc.isEmpty ? '' : '?hc=$hc'}');
              },
              icon: const Icon(Icons.add),
              label: const Text('Registrar paciente nuevo'),
            ),
          ],
        ),
      ),
    );
  }
}
