import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/widgets/common.dart';
import '../../data/mock/seed_data.dart';
import '../../providers/repository_providers.dart';
import 'auth_widgets.dart';

/// Pantalla 01 · Inicio de sesión con error genérico (HU02, HU04·CA2).
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _obscure = true;
  bool _loading = false;
  String? _error;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    FocusScope.of(context).unfocus();
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      await ref.read(authRepositoryProvider).signIn(_email.text, _password.text);
    } on AppException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _openActivation() async {
    final controller = TextEditingController(text: _email.text);
    final email = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Enlace de activación'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Abre el enlace que recibiste por correo. En esta versión de demostración, '
              'ingresa el correo con el que el administrador te dio de alta.',
              style: TextStyle(fontSize: 14, color: AppColors.textMuted, height: 1.4),
            ),
            const SizedBox(height: 14),
            TextField(
              controller: controller,
              keyboardType: TextInputType.emailAddress,
              decoration: const InputDecoration(hintText: 'correo@hospital.gob.pe'),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancelar')),
          TextButton(
              onPressed: () => Navigator.pop(ctx, controller.text),
              child: const Text('Abrir enlace')),
        ],
      ),
    );
    if (email == null || email.trim().isEmpty || !mounted) return;
    final ticket = await ref.read(authRepositoryProvider).findActivation(email);
    if (!mounted) return;
    if (ticket == null) {
      showAppSnack(context, 'No hay un enlace de activación pendiente para ese correo.',
          error: true);
      return;
    }
    context.push('/activar/${ticket.uid}');
  }

  void _showDemoAccounts() {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.white,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (ctx) {
        Widget tile(String title, String email, String pw) => ListTile(
              title: Text(title, style: const TextStyle(fontWeight: FontWeight.w600)),
              subtitle: Text('$email · $pw'),
              onTap: () {
                _email.text = email;
                _password.text = pw;
                Navigator.pop(ctx);
              },
            );
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Padding(
                padding: EdgeInsets.fromLTRB(20, 20, 20, 4),
                child: Text('Cuentas de demostración',
                    style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
              ),
              tile('Médico especialista', DemoCredentials.specialistEmail,
                  DemoCredentials.specialistPassword),
              tile('Administrador', DemoCredentials.adminEmail, DemoCredentials.adminPassword),
              tile('Especialista con acceso revocado', DemoCredentials.revokedEmail,
                  DemoCredentials.specialistPassword),
              const Padding(
                padding: EdgeInsets.fromLTRB(20, 4, 20, 20),
                child: Text(
                  'Cuenta pendiente de activación: ${DemoCredentials.pendingEmail} '
                  '(usa "Tengo un enlace de activación").',
                  style: TextStyle(fontSize: 13, color: AppColors.textSubtle),
                ),
              ),
            ],
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: BottomPinnedScroll(
          padding: const EdgeInsets.fromLTRB(24, 40, 24, 24),
          children: [
            const DermaviaLogo(),
            const SizedBox(height: 14),
            const ScreenTitle(
              'Te damos la bienvenida',
              size: 28,
              subtitle:
                  'Ingresa con la cuenta que te asignó el administrador de tu establecimiento.',
            ),
            const SizedBox(height: 28),
            if (_error != null) ...[
              InfoBanner(
                key: const Key('login-error'),
                message: _error!,
                tone: BannerTone.error,
                leading: const AlertDot(),
              ),
              const SizedBox(height: 20),
            ],
            AutofillGroup(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  AppTextField(
                    label: 'Correo institucional',
                    controller: _email,
                    keyboardType: TextInputType.emailAddress,
                    autofillHints: const [AutofillHints.email],
                    hint: 'nombre@hospital.gob.pe',
                  ),
                  const SizedBox(height: 16),
                  AppTextField(
                    label: 'Contraseña',
                    controller: _password,
                    obscureText: _obscure,
                    autofillHints: const [AutofillHints.password],
                    suffix: TextButton(
                      onPressed: () => setState(() => _obscure = !_obscure),
                      child: Text(_obscure ? 'Mostrar' : 'Ocultar'),
                    ),
                  ),
                ],
              ),
            ),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                onPressed: () => context.push('/recuperar'),
                child: const Text('¿Olvidaste tu contraseña?'),
              ),
            ),
          ],
          bottom: [
            PrimaryButton(label: 'Iniciar sesión', loading: _loading, onPressed: _submit),
            const SizedBox(height: 8),
            TextButton(
              onPressed: _openActivation,
              child: const Text('Tengo un enlace de activación'),
            ),
            const Text(
              'No existe registro público. Si aún no tienes cuenta, solicítala al administrador del sistema.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 13, color: AppColors.textSubtle, height: 1.45),
            ),
            TextButton(
              onPressed: _showDemoAccounts,
              style: TextButton.styleFrom(foregroundColor: AppColors.textSubtle),
              child: const Text('Cuentas de demostración'),
            ),
          ],
        ),
      ),
    );
  }
}
