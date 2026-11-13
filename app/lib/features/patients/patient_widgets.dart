import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_colors.dart';
import '../../core/widgets/common.dart';
import '../../domain/models/patient.dart';
import '../../providers/case_providers.dart';

/// Inicia un caso para el paciente: si no hay consentimiento vigente pasa
/// primero por la pantalla de consentimiento (RF-02.6).
void startCaseFor(BuildContext context, WidgetRef ref, Patient patient,
    {bool replace = false}) {
  if (!patient.hasValidConsent) {
    final route = '/paciente/${patient.id}/consentimiento';
    replace ? context.pushReplacement(route) : context.push(route);
    return;
  }
  ref.read(captureDraftProvider.notifier)
    ..reset()
    ..start(patient.id);
  final route = '/captura/${patient.id}';
  replace ? context.pushReplacement(route) : context.push(route);
}

/// Encabezado con avatar, nombre y datos demográficos.
class PatientHeader extends StatelessWidget {
  const PatientHeader({super.key, required this.patient, required this.now, this.big = false});
  final Patient patient;
  final DateTime now;
  final bool big;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        InitialsAvatar(patient.initials, size: big ? 52 : 44),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(patient.nombres,
                  style: TextStyle(fontWeight: FontWeight.w700, fontSize: big ? 18 : 16)),
              const SizedBox(height: 2),
              Text(
                '${patient.sexo.short} · ${patient.ageAt(now)} años · Fototipo ${patient.fototipo.roman}',
                style: const TextStyle(fontSize: 13, color: AppColors.textSubtle),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class ConsentChip extends StatelessWidget {
  const ConsentChip({super.key, required this.patient});
  final Patient patient;

  @override
  Widget build(BuildContext context) {
    final c = patient.consent;
    if (c == null) return const StatusChip('Sin consentimiento', tone: ChipTone.warning);
    if (!c.vigente) return const StatusChip('Consentimiento revocado', tone: ChipTone.error);
    return const StatusChip('Consentimiento vigente', tone: ChipTone.success);
  }
}
