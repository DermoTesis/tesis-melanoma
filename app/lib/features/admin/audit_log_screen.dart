import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../core/widgets/common.dart';
import '../../domain/models/audit_event.dart';
import '../../providers/repository_providers.dart';

/// Bitácora completa de eventos críticos (RNF-17).
class AuditLogScreen extends ConsumerWidget {
  const AuditLogScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final events = ref.watch(auditEventsProvider).value ?? const <AuditEvent>[];
    return Scaffold(
      appBar: AppBar(title: const Text('Bitácora de auditoría')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(18, 0, 18, 24),
        children: [
          const InfoBanner(
            message:
                'Registro de solo lectura con retención bloqueada en Cloud Logging. Incluye altas de cuentas, '
                'consentimientos, validaciones, cierres y eliminación de datos.',
          ),
          const SizedBox(height: 12),
          AuditEventsCard(events: events, detailed: true),
        ],
      ),
    );
  }
}

class AuditEventsCard extends StatelessWidget {
  const AuditEventsCard({super.key, required this.events, this.detailed = false});
  final List<AuditEvent> events;
  final bool detailed;

  @override
  Widget build(BuildContext context) {
    if (events.isEmpty) return const InfoBanner(message: 'Sin eventos registrados.');
    return AppCard(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
      child: Column(
        children: [
          for (var i = 0; i < events.length; i++)
            Container(
              padding: const EdgeInsets.symmetric(vertical: 10),
              decoration: BoxDecoration(
                border: i == events.length - 1
                    ? null
                    : const Border(bottom: BorderSide(color: AppColors.surfaceMuted)),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(events[i].summary, style: const TextStyle(fontSize: 12)),
                        if (detailed)
                          Text(events[i].actorName,
                              style: const TextStyle(fontSize: 11, color: AppColors.textSubtle)),
                      ],
                    ),
                  ),
                  const SizedBox(width: 10),
                  Text(
                    detailed
                        ? Fmt.dateTime(events[i].timestamp)
                        : Fmt.time(events[i].timestamp),
                    style: AppFonts.mono(fontSize: 11),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
