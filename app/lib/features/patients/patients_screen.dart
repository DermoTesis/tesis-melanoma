import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/common.dart';
import '../../providers/repository_providers.dart';
import '../dashboard/case_widgets.dart';
import 'patient_widgets.dart';

/// Lista de pacientes atendidos (pestaña Pacientes).
class PatientsScreen extends ConsumerStatefulWidget {
  const PatientsScreen({super.key});

  @override
  ConsumerState<PatientsScreen> createState() => _PatientsScreenState();
}

class _PatientsScreenState extends ConsumerState<PatientsScreen> {
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final patientsAsync = ref.watch(patientsProvider);
    final now = ref.watch(clockProvider)();
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => context.push('/nuevo-caso'),
        backgroundColor: AppColors.primary,
        foregroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
        icon: const Icon(Icons.add),
        label: const Text('Nuevo caso', style: TextStyle(fontWeight: FontWeight.w600)),
      ),
      body: Column(
        children: [
          const SafeArea(bottom: false, child: OfflineBanner()),
          Padding(
            padding: const EdgeInsets.fromLTRB(18, 14, 18, 10),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text('Pacientes',
                    style: TextStyle(fontSize: 22, fontWeight: FontWeight.w700)),
                const SizedBox(height: 14),
                TextField(
                  onChanged: (v) => setState(() => _query = v.trim().toLowerCase()),
                  decoration: const InputDecoration(
                    hintText: 'Buscar por nombre o historia clínica',
                    prefixIcon: Icon(Icons.search, color: AppColors.textSubtle),
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: patientsAsync.when(
              loading: () => const LoadingView(),
              error: (e, _) => ErrorView('$e'),
              data: (all) {
                final list = all
                    .where((p) =>
                        _query.isEmpty ||
                        p.nombres.toLowerCase().contains(_query) ||
                        p.numeroHistoriaClinica.toLowerCase().contains(_query))
                    .toList();
                if (list.isEmpty) {
                  return const Center(
                    child: Text('Sin resultados',
                        style: TextStyle(color: AppColors.textSubtle)),
                  );
                }
                return ListView.separated(
                  padding: const EdgeInsets.fromLTRB(18, 4, 18, 96),
                  itemCount: list.length,
                  separatorBuilder: (_, _) => const SizedBox(height: 10),
                  itemBuilder: (context, i) {
                    final p = list[i];
                    return AppCard(
                      padding: const EdgeInsets.all(14),
                      onTap: () => context.push('/paciente/${p.id}'),
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
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
