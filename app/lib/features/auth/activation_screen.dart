import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../core/widgets/common.dart';
import '../../data/mock/mock_repositories.dart';
import '../../domain/models/user.dart';
import '../../providers/repository_providers.dart';
import 'auth_widgets.dart';

/// Pantalla 02 · Activación de cuenta, paso 1 de 2 (HU01·CA1).
class ActivationScreen extends ConsumerStatefulWidget {
  const ActivationScreen({super.key, required this.uid});
  final String uid;

  @override
  ConsumerState<ActivationScreen> createState() => _ActivationScreenState();
}

class _ActivationScreenState extends ConsumerState<ActivationScreen> {
  final _password = TextEditingController();
  final _confirm = TextEditingController();
  ActivationTicket? _ticket;
  bool _loadingTicket = true;
  bool _saving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _password.addListener(() => setState(() {}));
    _confirm.addListener(() => setState(() {}));
    ref.read(authRepositoryProvider).getActivation(widget.uid).then((t) {
      if (!mounted) return;
      setState(() {
        _ticket = t;
        _loadingTicket = false;
      });
    });
  }

  @override
  void dispose() {
    _password.dispose();
    _confirm.dispose();
    super.dispose();
  }

  Future<void> _continue() async {
    final pw = _password.text;
    if (!PasswordPolicy.isValid(pw)) {
      setState(() => _error = 'La contraseña no cumple todos los requisitos.');
      return;
    }
    if (pw != _confirm.text) {
      setState(() => _error = 'Las contraseñas no coinciden.');
      return;
    }
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      // Al activar, el router redirige al paso 2 (aceptación del alcance).
      await ref.read(authRepositoryProvider).activateAccount(widget.uid, pw);
    } on AppException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final now = ref.watch(clockProvider)();
    final ticket = _ticket;
    final pw = _password.text;
    return Scaffold(
      appBar: AppBar(),
      body: SafeArea(
        top: false,
        child: _loadingTicket
            ? const LoadingView()
            : ticket == null
                ? const ErrorView('El enlace de activación no es válido o ya fue utilizado.')
                : BottomPinnedScroll(
                    padding: const EdgeInsets.fromLTRB(24, 4, 24, 24),
                    children: [
                      const StepProgress(total: 2, current: 1),
                      const SizedBox(height: 24),
                      ScreenTitle(
                        'Hola, ${ticket.nombres}',
                        eyebrow: 'Paso 1 de 2',
                        subtitle:
                            'Tu cuenta fue dada de alta por el administrador. Define una contraseña para activarla.',
                      ),
                      const SizedBox(height: 22),
                      _ValidityBox(
                        expired: ticket.isExpired(now),
                        remaining: ticket.expiresAt.difference(now),
                      ),
                      const SizedBox(height: 22),
                      if (_error != null) ...[
                        InfoBanner(
                            message: _error!, tone: BannerTone.error, leading: const AlertDot()),
                        const SizedBox(height: 16),
                      ],
                      AppTextField(
                          label: 'Nueva contraseña', controller: _password, obscureText: true),
                      const SizedBox(height: 14),
                      AppTextField(
                          label: 'Confirmar contraseña', controller: _confirm, obscureText: true),
                      const SizedBox(height: 18),
                      CheckLine(text: 'Mínimo 10 caracteres', ok: PasswordPolicy.hasMinLength(pw)),
                      CheckLine(
                          text: 'Una mayúscula y un número',
                          ok: PasswordPolicy.hasUpperAndNumber(pw)),
                      CheckLine(text: 'Un carácter especial', ok: PasswordPolicy.hasSpecial(pw)),
                      CheckLine(
                          text: 'Ambas contraseñas coinciden',
                          ok: pw.isNotEmpty && pw == _confirm.text),
                    ],
                    bottom: [
                      PrimaryButton(
                        label: 'Continuar',
                        loading: _saving,
                        onPressed: ticket.isExpired(now) ? null : _continue,
                      ),
                    ],
                  ),
      ),
    );
  }
}

class _ValidityBox extends StatelessWidget {
  const _ValidityBox({required this.expired, required this.remaining});
  final bool expired;
  final Duration remaining;

  @override
  Widget build(BuildContext context) {
    if (expired) {
      return const InfoBanner(
        tone: BannerTone.warning,
        title: 'Enlace vencido',
        message: 'Solicita al administrador un nuevo enlace de activación.',
      );
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration:
          BoxDecoration(color: AppColors.successBg, borderRadius: BorderRadius.circular(12)),
      child: Row(
        children: [
          const Expanded(
            child: Text('Enlace de activación vigente',
                style: TextStyle(fontSize: 13, color: AppColors.primaryDark)),
          ),
          Text(Fmt.countdown(remaining),
              style: AppFonts.mono(
                  fontSize: 13, color: AppColors.primaryDark, fontWeight: FontWeight.w500)),
        ],
      ),
    );
  }
}
