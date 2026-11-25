import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/common.dart';
import '../../providers/repository_providers.dart';
import 'auth_widgets.dart';

/// Pantalla 03 · Aceptación del alcance (HU01·CA2, RF-05.3, RNF-06).
class ScopeAcceptanceScreen extends ConsumerStatefulWidget {
  const ScopeAcceptanceScreen({super.key});

  @override
  ConsumerState<ScopeAcceptanceScreen> createState() => _ScopeAcceptanceScreenState();
}

class _ScopeAcceptanceScreenState extends ConsumerState<ScopeAcceptanceScreen> {
  bool _accepted = false;
  bool _saving = false;

  Future<void> _accept() async {
    setState(() => _saving = true);
    try {
      await ref.read(authRepositoryProvider).acceptScope();
    } on AppException catch (e) {
      if (mounted) showAppSnack(context, e.message, error: true);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    Widget point(String n, InlineSpan text) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 6),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                width: 22,
                child: Text(n, style: AppFonts.mono(fontSize: 13, color: AppColors.primary)),
              ),
              Expanded(
                child: Text.rich(text,
                    style: const TextStyle(
                        fontSize: 14, height: 1.5, color: AppColors.textBody)),
              ),
            ],
          ),
        );

    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        actions: [
          TextButton(
            onPressed: () => ref.read(authRepositoryProvider).signOut(),
            child: const Text('Salir'),
          ),
        ],
      ),
      body: SafeArea(
        top: false,
        child: BottomPinnedScroll(
          padding: const EdgeInsets.fromLTRB(24, 4, 24, 24),
          children: [
            const StepProgress(total: 2, current: 2),
            const SizedBox(height: 24),
            const ScreenTitle('Una herramienta de apoyo, no de diagnóstico',
                eyebrow: 'Paso 2 de 2'),
            const SizedBox(height: 22),
            AppCard(
              padding: const EdgeInsets.all(18),
              child: Column(
                children: [
                  point(
                    '1',
                    const TextSpan(children: [
                      TextSpan(text: 'Dermavía genera una '),
                      TextSpan(
                          text: 'predicción preliminar',
                          style: TextStyle(fontWeight: FontWeight.w700)),
                      TextSpan(text: ' (posible melanoma o sin alerta) con un riesgo estimado en porcentaje.'),
                    ]),
                  ),
                  point(
                      '2',
                      const TextSpan(
                          text:
                              'Solo evalúa melanoma, a partir de dos fotos dermatoscópicas: no descarta '
                              'otros cánceres de piel. Se desarrolló con dermatoscopias de Austria y '
                              'Australia y aún no se ha validado con dermatoscopio de clip para celular '
                              'ni en pacientes peruanos.')),
                  point(
                      '3',
                      const TextSpan(
                          text:
                              'Ningún caso se cierra ni se exporta sin tu validación y sustento clínico.')),
                  point(
                      '4',
                      const TextSpan(
                          text:
                              'No reemplaza tu criterio médico ni los exámenes clínicos pertinentes. No agenda citas ni brinda telemedicina.')),
                ],
              ),
            ),
            const SizedBox(height: 22),
            CheckLine(
              text:
                  'Entiendo y acepto que la herramienta es de apoyo diagnóstico y no reemplaza el criterio médico.',
              ok: _accepted,
              onTap: () => setState(() => _accepted = !_accepted),
            ),
          ],
          bottom: [
            const Text('Se registrará la fecha y hora de tu aceptación.',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 12, color: AppColors.textSubtle)),
            const SizedBox(height: 12),
            PrimaryButton(
              label: 'Aceptar y activar cuenta',
              loading: _saving,
              onPressed: _accepted ? _accept : null,
            ),
          ],
        ),
      ),
    );
  }
}
