import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/utils/formatters.dart';
import '../../core/widgets/common.dart';
import '../../domain/models/patient.dart';
import '../../providers/repository_providers.dart';
import '../auth/auth_widgets.dart';
import 'patient_widgets.dart';

/// Pantalla 09 · Consentimiento informado (HU07, RF-02.6, RNF-05, RNF-06).
class ConsentScreen extends ConsumerStatefulWidget {
  const ConsentScreen({super.key, required this.patientId});
  final String patientId;

  @override
  ConsumerState<ConsentScreen> createState() => _ConsentScreenState();
}

class _ConsentScreenState extends ConsumerState<ConsentScreen> {
  final _checks = [false, false, false];
  bool _accepts = false;
  bool _saving = false;

  bool get _ready => _accepts && _checks.every((c) => c);

  Future<void> _register() async {
    setState(() => _saving = true);
    try {
      final patient =
          await ref.read(patientRepositoryProvider).registerConsent(widget.patientId);
      if (!mounted) return;
      startCaseFor(context, ref, patient, replace: true);
    } on AppException catch (e) {
      if (mounted) showAppSnack(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final patientAsync = ref.watch(patientProvider(widget.patientId));
    final user = ref.watch(authStateProvider).value;
    final now = ref.watch(clockProvider)();
    const texts = [
      'Se fotografiará su lesión para un análisis de apoyo diagnóstico.',
      'El resultado es preliminar y lo valida su médico especialista.',
      'Sus datos se tratan conforme a la Ley N.° 29733 y puede revocar este consentimiento.',
    ];

    return Scaffold(
      appBar: AppBar(title: const Text('Consentimiento')),
      body: SafeArea(
        top: false,
        child: patientAsync.when(
          loading: () => const LoadingView(),
          error: (e, _) => ErrorView('$e'),
          data: (patient) {
            if (patient == null) return const ErrorView('Paciente no encontrado.');
            final pronoun = patient.sexo == Sex.femenino ? 'La paciente' : 'El paciente';
            return BottomPinnedScroll(
              padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
              children: [
                const StepProgress(total: 4, current: 2),
                const SizedBox(height: 16),
                InfoBanner(
                  tone: BannerTone.warning,
                  message: patient.consent?.fechaRevocacion != null
                      ? '${patient.nombres} revocó su consentimiento el ${Fmt.date(patient.consent!.fechaRevocacion!)}. Registra uno nuevo para habilitar la captura.'
                      : '${patient.nombres} no tiene consentimiento vigente. La captura se habilitará al registrarlo.',
                ),
                const SizedBox(height: 18),
                Text('Confirma con ${pronoun.toLowerCase()}',
                    style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                const SizedBox(height: 10),
                for (var i = 0; i < texts.length; i++)
                  CheckLine(
                    text: texts[i],
                    ok: _checks[i],
                    onTap: () => setState(() => _checks[i] = !_checks[i]),
                  ),
                const SizedBox(height: 14),
                AppCard(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    children: [
                      KeyValueRow('Fecha', Fmt.dateTime(now), mono: true),
                      KeyValueRow('Médico responsable', user?.nombres ?? '', bold: true),
                      Row(
                        children: [
                          Expanded(
                            child: Text('$pronoun acepta',
                                style: const TextStyle(
                                    fontSize: 13, color: AppColors.textSubtle)),
                          ),
                          Switch(
                            value: _accepts,
                            onChanged: (v) => setState(() => _accepts = v),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
              bottom: [
                PrimaryButton(
                  label: 'Registrar y habilitar captura',
                  loading: _saving,
                  onPressed: _ready ? _register : null,
                ),
                if (!_ready)
                  const Padding(
                    padding: EdgeInsets.only(top: 10),
                    child: Text(
                      'Marca cada punto y la aceptación para continuar.',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 12, color: AppColors.textSubtle),
                    ),
                  ),
              ],
            );
          },
        ),
      ),
    );
  }
}
