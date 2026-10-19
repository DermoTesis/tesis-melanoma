import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_colors.dart';
import '../../providers/case_providers.dart';

/// Navegación inferior del especialista: Casos · Pacientes · Alertas · Perfil.
class HomeShell extends ConsumerWidget {
  const HomeShell({super.key, required this.shell});
  final StatefulNavigationShell shell;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final overdue = ref.watch(overdueCasesProvider).length;
    return Scaffold(
      body: shell,
      bottomNavigationBar: DecoratedBox(
        decoration: const BoxDecoration(
            border: Border(top: BorderSide(color: AppColors.divider))),
        child: NavigationBar(
          selectedIndex: shell.currentIndex,
          onDestinationSelected: (i) =>
              shell.goBranch(i, initialLocation: i == shell.currentIndex),
          destinations: [
            const NavigationDestination(
                icon: Icon(Icons.folder_outlined),
                selectedIcon: Icon(Icons.folder),
                label: 'Casos'),
            const NavigationDestination(
                icon: Icon(Icons.people_outline),
                selectedIcon: Icon(Icons.people),
                label: 'Pacientes'),
            NavigationDestination(
              icon: Badge(
                isLabelVisible: overdue > 0,
                label: Text('$overdue'),
                backgroundColor: AppColors.error,
                child: const Icon(Icons.notifications_none),
              ),
              selectedIcon: Badge(
                isLabelVisible: overdue > 0,
                label: Text('$overdue'),
                backgroundColor: AppColors.error,
                child: const Icon(Icons.notifications),
              ),
              label: 'Alertas',
            ),
            const NavigationDestination(
                icon: Icon(Icons.person_outline),
                selectedIcon: Icon(Icons.person),
                label: 'Perfil'),
          ],
        ),
      ),
    );
  }
}
