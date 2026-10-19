import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_colors.dart';
import '../../core/utils/formatters.dart';
import '../../core/widgets/common.dart';
import '../../data/mock/mock_inference_engine.dart';
import '../../domain/models/report.dart';
import '../../providers/repository_providers.dart';
import '../dashboard/case_widgets.dart';

/// Perfil del especialista, cierre de sesión y simulación de conectividad.
class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(authStateProvider).value;
    final online = ref.watch(onlineProvider).value ?? true;
    if (user == null) return const SizedBox.shrink();

    return Scaffold(
      body: Column(
        children: [
          const SafeArea(bottom: false, child: OfflineBanner()),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(18, 14, 18, 24),
              children: [
                const Text('Perfil', style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
                const SizedBox(height: 16),
                AppCard(
                  child: Row(
                    children: [
                      InitialsAvatar(user.initials, size: 52),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(user.nombres,
                                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 17)),
                            Text(user.correo,
                                style: const TextStyle(fontSize: 13, color: AppColors.textSubtle)),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
                AppCard(
                  child: Column(
                    children: [
                      KeyValueRow('Establecimiento', user.establecimiento),
                      KeyValueRow('Colegiatura (CMP)', user.cmp ?? '—', mono: true),
                      if (user.fechaVerificacion != null)
                        KeyValueRow('Verificado', Fmt.date(user.fechaVerificacion!), mono: true),
                      if (user.termsAcceptedAt != null)
                        KeyValueRow('Alcance aceptado', Fmt.dateTime(user.termsAcceptedAt!), mono: true),
                      const KeyValueRow('Modelo activo', ModelArtifact.version, mono: true),
                    ],
                  ),
                ),
                const SizedBox(height: 12),
                const InfoBanner(message: kScopeNotice),
                const SizedBox(height: 20),
                const SectionLabel('DEMOSTRACIÓN'),
                const SizedBox(height: 8),
                AppCard(
                  padding: const EdgeInsets.fromLTRB(16, 6, 8, 6),
                  child: Row(
                    children: [
                      const Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('Simular sin conexión',
                                style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
                            Text('Los casos se guardan en el dispositivo y se envían al reconectar.',
                                style: TextStyle(fontSize: 12, color: AppColors.textSubtle)),
                          ],
                        ),
                      ),
                      Switch(
                        value: !online,
                        onChanged: (v) => ref.read(connectivityServiceProvider).setOnline(!v),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 24),
                SecondaryButton(
                  label: 'Cerrar sesión',
                  icon: Icons.logout,
                  onPressed: () => ref.read(authRepositoryProvider).signOut(),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
