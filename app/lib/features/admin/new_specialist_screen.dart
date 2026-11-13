import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/utils/formatters.dart';
import '../../core/widgets/common.dart';
import '../../providers/repository_providers.dart';
import '../auth/auth_widgets.dart';

/// Pantalla 21 · Alta de especialista con verificación de colegiatura
/// (HU04, RF-01.3, RNF-17).
class NewSpecialistScreen extends ConsumerStatefulWidget {
  const NewSpecialistScreen({super.key});

  @override
  ConsumerState<NewSpecialistScreen> createState() => _NewSpecialistScreenState();
}

class _NewSpecialistScreenState extends ConsumerState<NewSpecialistScreen> {
  final _formKey = GlobalKey<FormState>();
  final _names = TextEditingController();
  final _email = TextEditingController();
  final _dni = TextEditingController();
  final _cmp = TextEditingController();
  bool _verified = false;
  bool _attempted = false;
  bool _saving = false;

  @override
  void dispose() {
    _names.dispose();
    _email.dispose();
    _dni.dispose();
    _cmp.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() => _attempted = true);
    if (!_formKey.currentState!.validate() || !_verified) return;
    setState(() => _saving = true);
    try {
      final ticket = await ref.read(adminRepositoryProvider).createSpecialist(
            nombres: _names.text,
            correo: _email.text,
            dni: _dni.text,
            cmp: _cmp.text,
            colegiaturaVerificada: _verified,
          );
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Especialista dado de alta'),
          content: Text(
            'Se envió un enlace de activación a ${ticket.correo}, vigente hasta el '
            '${Fmt.dateTime(ticket.expiresAt)}.\n\nDemo: el especialista puede activar su cuenta '
            'desde "Tengo un enlace de activación" en el inicio de sesión.',
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Entendido')),
          ],
        ),
      );
      if (mounted) context.pop();
    } on AppException catch (e) {
      if (mounted) showAppSnack(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final admin = ref.watch(authStateProvider).value;
    final now = ref.watch(clockProvider)();
    String? required(String? v) => (v == null || v.trim().isEmpty) ? 'Campo obligatorio' : null;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Nuevo especialista'),
        actions: const [
          Padding(padding: EdgeInsets.only(right: 16), child: StatusChip('Admin', tone: ChipTone.success)),
        ],
      ),
      body: SafeArea(
        top: false,
        child: Form(
          key: _formKey,
          child: BottomPinnedScroll(
            padding: const EdgeInsets.fromLTRB(20, 4, 20, 22),
            children: [
              AppTextField(
                label: 'Nombres y apellidos',
                controller: _names,
                textCapitalization: TextCapitalization.words,
                validator: required,
              ),
              const SizedBox(height: 13),
              AppTextField(
                label: 'Correo institucional',
                controller: _email,
                keyboardType: TextInputType.emailAddress,
                validator: (v) {
                  if (required(v) != null) return required(v);
                  return v!.contains('@') ? null : 'Correo no válido';
                },
              ),
              const SizedBox(height: 13),
              AppTextField(
                label: 'DNI',
                controller: _dni,
                keyboardType: TextInputType.number,
                validator: (v) =>
                    RegExp(r'^\d{8}$').hasMatch(v?.trim() ?? '') ? null : 'El DNI tiene 8 dígitos',
              ),
              const SizedBox(height: 13),
              AppTextField(
                label: 'N.° de colegiatura (CMP)',
                controller: _cmp,
                mono: true,
                keyboardType: TextInputType.number,
                validator: required,
              ),
              const SizedBox(height: 14),
              AppCard(
                padding: const EdgeInsets.all(14),
                border: _attempted && !_verified
                    ? Border.all(color: AppColors.errorBorder, width: 1.5)
                    : null,
                child: Column(
                  children: [
                    CheckLine(
                      text: 'Verifiqué la habilitación ante el Colegio Médico del Perú',
                      ok: _verified,
                      onTap: () => setState(() => _verified = !_verified),
                    ),
                    const SizedBox(height: 6),
                    KeyValueRow('Fecha de verificación', Fmt.date(now), mono: true),
                    KeyValueRow('Responsable', '${admin?.nombres ?? ''} (admin)', bold: true),
                    const KeyValueRow('Rol', 'Médico especialista', bold: true),
                  ],
                ),
              ),
            ],
            bottom: [
              const Text('Se enviará un enlace de activación con vigencia limitada.',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 12, color: AppColors.textSubtle)),
              const SizedBox(height: 8),
              PrimaryButton(label: 'Dar de alta', loading: _saving, onPressed: _submit),
            ],
          ),
        ),
      ),
    );
  }
}
