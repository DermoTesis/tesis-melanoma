import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme/app_colors.dart';
import '../../core/widgets/common.dart';
import '../../domain/models/clinical_case.dart';
import '../../domain/models/patient.dart';
import '../../providers/case_providers.dart';
import '../../providers/repository_providers.dart';
import 'case_widgets.dart';

enum PanelFilter { pendientes, enAnalisis, validados, error }

extension on PanelFilter {
  String get label => switch (this) {
        PanelFilter.pendientes => 'Pendientes',
        PanelFilter.enAnalisis => 'En análisis',
        PanelFilter.validados => 'Validados',
        PanelFilter.error => 'Error',
      };

  bool matches(ClinicalCase c) => switch (this) {
        PanelFilter.pendientes => c.status == CaseStatus.pendienteValidacion,
        PanelFilter.enAnalisis =>
          c.status == CaseStatus.registrado || c.status == CaseStatus.enAnalisis,
        PanelFilter.validados =>
          c.status == CaseStatus.validado || c.status == CaseStatus.cerrado,
        PanelFilter.error => c.status == CaseStatus.errorAnalisis,
      };
}

/// Pantalla 05 · Panel priorizado de casos (HU24, HU25, HU30, RF-05.1, RF-06.2).
class CasesPanelScreen extends ConsumerStatefulWidget {
  const CasesPanelScreen({super.key});

  @override
  ConsumerState<CasesPanelScreen> createState() => _CasesPanelScreenState();
}

class _CasesPanelScreenState extends ConsumerState<CasesPanelScreen> {
  PanelFilter _filter = PanelFilter.pendientes;
  bool _reordering = false;
  List<ClinicalCase>? _reorderBuffer;

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(authStateProvider).value;
    final casesAsync = ref.watch(myCasesProvider);
    final patients = {
      for (final p in ref.watch(patientsProvider).value ?? const <Patient>[]) p.id: p
    };
    final overdue = ref.watch(overdueCasesProvider);
    final now = ref.watch(clockProvider)();
    final repo = ref.read(caseRepositoryProvider);

    return Scaffold(
      floatingActionButton: _reordering
          ? null
          : FloatingActionButton.extended(
              heroTag: 'fab-casos',
              onPressed: () => context.push('/nuevo-caso'),
              backgroundColor: AppColors.primary,
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
              icon: const Icon(Icons.add),
              label: const Text('Nuevo caso', style: TextStyle(fontWeight: FontWeight.w600)),
            ),
      body: Column(
        children: [
          SafeArea(bottom: false, child: const OfflineBanner()),
          Expanded(
            child: casesAsync.when(
              loading: () => const LoadingView(),
              error: (e, _) => ErrorView('$e'),
              data: (all) {
                final counts = {
                  for (final f in PanelFilter.values) f: all.where(f.matches).length
                };
                final visible = _reorderBuffer ??
                    sortForPanel(all.where(_filter.matches).toList(), repo.manualOrder);
                return CustomScrollView(
                  slivers: [
                    SliverPadding(
                      padding: const EdgeInsets.fromLTRB(18, 14, 18, 0),
                      sliver: SliverList.list(children: [
                        _Header(
                            establishment: user?.establecimiento ?? '',
                            initials: user?.initials ?? '',
                            onAvatar: () => context.go('/perfil')),
                        const SizedBox(height: 14),
                        if (overdue.isNotEmpty) ...[
                          InfoBanner(
                            tone: BannerTone.error,
                            leading: AlertDot(text: '${overdue.length}', size: 20),
                            message:
                                '${overdue.length == 1 ? 'caso supera' : 'casos superan'} el tiempo límite de validación (${kValidationDeadline.inHours} h)',
                            trailing: const Text('Ver',
                                style: TextStyle(
                                    color: AppColors.errorText, fontWeight: FontWeight.w600)),
                            onTap: () => context.go('/alertas'),
                          ),
                          const SizedBox(height: 14),
                        ],
                        SingleChildScrollView(
                          scrollDirection: Axis.horizontal,
                          child: Row(
                            children: [
                              for (final f in PanelFilter.values)
                                Padding(
                                  padding: const EdgeInsets.only(right: 6),
                                  child: PillChip(
                                    label: '${f.label} ${counts[f]}',
                                    selected: f == _filter,
                                    onTap: () => setState(() {
                                      _filter = f;
                                      _reordering = false;
                                      _reorderBuffer = null;
                                    }),
                                  ),
                                ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 12),
                        if (_filter == PanelFilter.pendientes && visible.isNotEmpty)
                          _OrderBar(
                            reordering: _reordering,
                            manual: repo.manualOrder.isNotEmpty,
                            onReorder: () => setState(() {
                              _reordering = true;
                              _reorderBuffer = List.of(visible);
                            }),
                            onDone: () async {
                              final ids = _reorderBuffer!.map((c) => c.id).toList();
                              setState(() {
                                _reordering = false;
                                _reorderBuffer = null;
                              });
                              await repo.setManualOrder(ids);
                            },
                            onReset: () => repo.setManualOrder(const []),
                          ),
                        const SizedBox(height: 10),
                      ]),
                    ),
                    if (visible.isEmpty)
                      SliverFillRemaining(
                        hasScrollBody: false,
                        child: Padding(
                          padding: const EdgeInsets.all(32),
                          child: Text(
                            'No hay casos en "${_filter.label}".',
                            textAlign: TextAlign.center,
                            style: const TextStyle(color: AppColors.textSubtle),
                          ),
                        ),
                      )
                    else if (_reordering)
                      SliverReorderableList(
                        itemCount: visible.length,
                        onReorderItem: (from, to) => setState(() {
                          final item = _reorderBuffer!.removeAt(from);
                          _reorderBuffer!.insert(to > from ? to - 1 : to, item);
                        }),
                        itemBuilder: (context, i) {
                          final c = visible[i];
                          return Padding(
                            key: ValueKey(c.id),
                            padding: const EdgeInsets.fromLTRB(18, 0, 18, 10),
                            child: CaseCard(
                              clinicalCase: c,
                              patient: patients[c.patientId],
                              now: now,
                              trailing: ReorderableDragStartListener(
                                index: i,
                                child: const Icon(Icons.drag_handle,
                                    color: AppColors.textSubtle),
                              ),
                            ),
                          );
                        },
                      )
                    else
                      SliverPadding(
                        padding: const EdgeInsets.fromLTRB(18, 0, 18, 96),
                        sliver: SliverList.separated(
                          itemCount: visible.length,
                          separatorBuilder: (_, _) => const SizedBox(height: 10),
                          itemBuilder: (context, i) {
                            final c = visible[i];
                            return CaseCard(
                              clinicalCase: c,
                              patient: patients[c.patientId],
                              now: now,
                              onTap: () => context.push('/caso/${c.id}'),
                            );
                          },
                        ),
                      ),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.establishment, required this.initials, required this.onAvatar});
  final String establishment;
  final String initials;
  final VoidCallback onAvatar;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(establishment,
                  style: const TextStyle(fontSize: 13, color: AppColors.textSubtle)),
              const SizedBox(height: 2),
              const Text('Mis casos',
                  style: TextStyle(
                      fontSize: 22, fontWeight: FontWeight.w700, letterSpacing: -0.2)),
            ],
          ),
        ),
        GestureDetector(onTap: onAvatar, child: InitialsAvatar(initials)),
      ],
    );
  }
}

class _OrderBar extends StatelessWidget {
  const _OrderBar({
    required this.reordering,
    required this.manual,
    required this.onReorder,
    required this.onDone,
    required this.onReset,
  });

  final bool reordering;
  final bool manual;
  final VoidCallback onReorder;
  final VoidCallback onDone;
  final VoidCallback onReset;

  @override
  Widget build(BuildContext context) {
    const style = TextStyle(fontSize: 12, color: AppColors.textSubtle);
    const action = TextStyle(fontSize: 12, color: AppColors.primary, fontWeight: FontWeight.w600);
    return Row(
      children: [
        Expanded(
          child: Text(
            reordering
                ? 'Arrastra los casos para reordenarlos'
                : manual
                    ? 'Orden manual del especialista'
                    : 'Orden sugerido: mayor riesgo primero',
            style: style,
          ),
        ),
        if (!reordering && manual)
          GestureDetector(
              onTap: onReset,
              child: const Padding(
                padding: EdgeInsets.only(right: 14),
                child: Text('Restablecer', style: action),
              )),
        GestureDetector(
          onTap: reordering ? onDone : onReorder,
          child: Text(reordering ? 'Listo' : 'Reordenar', style: action),
        ),
      ],
    );
  }
}
