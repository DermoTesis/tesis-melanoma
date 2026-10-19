import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/common.dart';
import '../../data/mock/mock_repositories.dart';
import '../../domain/models/user.dart';
import '../../providers/repository_providers.dart';
import 'auth_widgets.dart';

/// Pantalla 04 · Recuperar contraseña con enlace de tiempo limitado (HU03).
class RecoverScreen extends ConsumerStatefulWidget {
  const RecoverScreen({super.key});

  @override
  ConsumerState<RecoverScreen> createState() => _RecoverScreenState();
}

class _RecoverScreenState extends ConsumerState<RecoverScreen> {
  final _email = TextEditingController();
  final _newPassword = TextEditingController();
  PasswordResetTicket? _ticket;
  bool _linkOpened = false;
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _newPassword.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _email.dispose();
    _newPassword.dispose();
    super.dispose();
  }

  Future<void> _request() async {
    if (_email.text.trim().isEmpty) {
      setState(() => _error = 'Ingresa tu correo institucional.');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
      _linkOpened = false;
    });
    final t = await ref.read(authRepositoryProvider).requestPasswordReset(_email.text);
    if (!mounted) return;
    setState(() {
      _ticket = t;
      _loading = false;
    });
  }

  Future<void> _reset() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await ref.read(authRepositoryProvider).resetPassword(_email.text, _newPassword.text);
      if (!mounted) return;
      showAppSnack(context, 'Contraseña actualizada. Inicia sesión.');
      context.pop();
    } on AppException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _simulateExpired() async {
    final t = await ref.read(authRepositoryProvider).expireResetLink(_email.text);
    if (mounted && t != null) setState(() => _ticket = t);
  }

  @override
  Widget build(BuildContext context) {
    final now = ref.watch(clockProvider)();
    final ticket = _ticket;
    final expired = ticket?.isExpired(now) ?? false;

    return Scaffold(
      appBar: AppBar(),
      body: SafeArea(
        top: false,
        child: BottomPinnedScroll(
          padding: const EdgeInsets.fromLTRB(24, 4, 24, 24),
          children: [
            ScreenTitle(
              ticket == null ? 'Recupera tu acceso' : 'Revisa tu correo',
              subtitle: ticket == null
                  ? 'Te enviaremos un enlace de tiempo limitado para restablecer tu contraseña.'
                  : 'Si el correo está registrado, recibirás un enlace para restablecer tu contraseña.',
            ),
            const SizedBox(height: 24),
            if (_error != null) ...[
              InfoBanner(message: _error!, tone: BannerTone.error, leading: const AlertDot()),
              const SizedBox(height: 16),
            ],
            if (ticket == null)
              AppTextField(
                label: 'Correo institucional',
                controller: _email,
                keyboardType: TextInputType.emailAddress,
                hint: 'nombre@hospital.gob.pe',
              )
            else ...[
              AppCard(
                padding: const EdgeInsets.all(18),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Enviado a',
                        style: TextStyle(fontSize: 13, color: AppColors.textSubtle)),
                    const SizedBox(height: 4),
                    Text(ticket.correo,
                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                    const Divider(height: 26),
                    Row(
                      children: [
                        const Expanded(
                          child: Text('Validez del enlace',
                              style: TextStyle(fontSize: 14, color: AppColors.textMuted)),
                        ),
                        Text(expired ? 'vencido' : '30 min',
                            style: AppFonts.mono(fontSize: 13, color: AppColors.text)),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 18),
              if (expired)
                const InfoBanner(
                  tone: BannerTone.warning,
                  title: 'Enlace vencido',
                  message: 'El enlace que abriste ya expiró y no puede usarse. Solicita uno nuevo.',
                )
              else if (_linkOpened) ...[
                AppTextField(
                    label: 'Nueva contraseña', controller: _newPassword, obscureText: true),
                const SizedBox(height: 12),
                CheckLine(
                    text: 'Mínimo 10 caracteres',
                    ok: PasswordPolicy.hasMinLength(_newPassword.text)),
                CheckLine(
                    text: 'Una mayúscula y un número',
                    ok: PasswordPolicy.hasUpperAndNumber(_newPassword.text)),
                CheckLine(
                    text: 'Un carácter especial',
                    ok: PasswordPolicy.hasSpecial(_newPassword.text)),
              ] else
                const InfoBanner(
                  message:
                      'Demo: el enlace del correo se simula con el botón "Abrir enlace recibido".',
                ),
            ],
          ],
          bottom: [
            if (ticket == null)
              PrimaryButton(label: 'Enviar enlace', loading: _loading, onPressed: _request)
            else if (expired) ...[
              PrimaryButton(label: 'Solicitar nuevo enlace', loading: _loading, onPressed: _request),
            ] else if (_linkOpened)
              PrimaryButton(
                label: 'Guardar contraseña',
                loading: _loading,
                onPressed: PasswordPolicy.isValid(_newPassword.text) ? _reset : null,
              )
            else ...[
              PrimaryButton(
                label: 'Abrir enlace recibido',
                onPressed: () => setState(() => _linkOpened = true),
              ),
              TextButton(
                onPressed: _simulateExpired,
                style: TextButton.styleFrom(foregroundColor: AppColors.textSubtle),
                child: const Text('Simular enlace vencido (demo)'),
              ),
            ],
            const SizedBox(height: 10),
            SecondaryButton(label: 'Volver a iniciar sesión', onPressed: () => context.pop()),
          ],
        ),
      ),
    );
  }
}
