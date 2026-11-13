import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/widgets/common.dart';
import '../../domain/models/user.dart';
import '../../providers/repository_providers.dart';
import 'audit_log_screen.dart';

/// Pantalla 22 · Usuarios, roles y bitácora (HU05, HU34·CA2, RF-01.4, RNF-17).
class AdminHomeScreen extends ConsumerWidget {
  const AdminHomeScreen({super.key});

  Future<void> _toggle(BuildContext context, WidgetRef ref, AppUser u, bool enabled) async {
    if (!enabled) {
      final ok = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Revocar acceso clínico'),
          content: Text('${u.nombres} dejará de acceder a pacientes, casos y validaciones. '
              'El cambio quedará en la bitácora.'),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancelar')),
            TextButton(
              style: TextButton.styleFrom(foregroundColor: AppColors.error),
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Revocar'),
            ),
          ],
        ),
      );
      if (ok != true) return;
    }
    try {
      await ref.read(adminRepositoryProvider).setClinicalAccess(u.uid, enabled);
    } on AppException catch (e) {
      if (context.mounted) showAppSnack(context, e.message, error: true);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final admin = ref.watch(authStateProvider).value;
    final users = ref.watch(usersProvider).value ?? const <AppUser>[];
    final events = ref.watch(auditEventsProvider).value ?? const [];

    return Scaffold(
      appBar: AppBar(
        title: const Text('Administración'),
        actions: [
          IconButton(
            tooltip: 'Cerrar sesión',
            icon: const Icon(Icons.logout),
            onPressed: () => ref.read(authRepositoryProvider).signOut(),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => context.push('/admin/nuevo'),
        backgroundColor: AppColors.primary,
        foregroundColor: Colors.white,
        icon: const Icon(Icons.person_add_alt_1),
        label: const Text('Nuevo especialista', style: TextStyle(fontWeight: FontWeight.w600)),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(18, 0, 18, 96),
        children: [
          Text('${admin?.nombres ?? ''} · ${admin?.establecimiento ?? ''}',
              style: const TextStyle(fontSize: 13, color: AppColors.textSubtle)),
          const SizedBox(height: 14),
          const Text('Usuarios', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
          const SizedBox(height: 12),
          AppCard(
            padding: EdgeInsets.zero,
            child: Column(
              children: [
                for (var i = 0; i < users.length; i++) ...[
                  _UserRow(
                    user: users[i],
                    onChanged: (v) => _toggle(context, ref, users[i], v),
                  ),
                  if (i < users.length - 1) const Divider(height: 1, color: AppColors.surfaceMuted),
                ],
              ],
            ),
          ),
          const SizedBox(height: 20),
          Row(
            children: [
              const Expanded(
                child: Text('Bitácora de auditoría',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
              ),
              TextButton(
                onPressed: () => context.push('/admin/bitacora'),
                child: const Text('Ver todo'),
              ),
            ],
          ),
          AuditEventsCard(events: events.take(6).toList()),
        ],
      ),
    );
  }
}

class _UserRow extends StatelessWidget {
  const _UserRow({required this.user, required this.onChanged});
  final AppUser user;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final (subtitle, color) = !user.clinicalAccess
        ? ('Acceso clínico revocado', AppColors.errorText)
        : user.status == AccountStatus.pendienteActivacion
            ? ('Pendiente de activación', AppColors.warningText)
            : ('Especialista · CMP ${user.cmp ?? '—'}', AppColors.textSubtle);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(user.nombres,
                    style: TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                      color: user.clinicalAccess ? AppColors.text : AppColors.textSubtle,
                    )),
                const SizedBox(height: 2),
                Text(subtitle, style: TextStyle(fontSize: 12, color: color)),
              ],
            ),
          ),
          Switch(value: user.clinicalAccess, onChanged: onChanged),
        ],
      ),
    );
  }
}
