import 'package:flutter/material.dart';

import '../../core/theme/app_colors.dart';

/// Asunto del correo que envía Firebase en la nube, tanto para activar una cuenta
/// como para recuperarla. Es su plantilla por defecto en español: Firebase no deja
/// personalizarla en este proyecto (CONEXION_NUBE.md, C2). "Dermavía" sale del nombre
/// público del proyecto en la consola de Firebase.
const kFirebaseEmailSubject = 'Cambia la contraseña de Dermavía';

/// Respuesta tras pedir un enlace por correo en la nube (I15, I16): no revela
/// si la cuenta existe (HU04·CA2). El enlace lo envía Firebase y vence en 1 h.
const kPasswordLinkSent =
    'Si la cuenta existe, te enviamos un enlace para definir tu contraseña. Busca el correo '
    '«$kFirebaseEmailSubject» (revisa también la carpeta de spam). Vence en 1 hora.';

class DermaviaLogo extends StatelessWidget {
  const DermaviaLogo({super.key, this.size = 56});
  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: AppColors.primary,
        borderRadius: BorderRadius.circular(size * 0.29),
      ),
      child: Text('D',
          style: TextStyle(
              color: Colors.white, fontWeight: FontWeight.w700, fontSize: size * 0.46)),
    );
  }
}

class ScreenTitle extends StatelessWidget {
  const ScreenTitle(this.title, {super.key, this.subtitle, this.eyebrow, this.size = 26});
  final String title;
  final String? subtitle;
  final String? eyebrow;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (eyebrow != null) ...[
          Text(eyebrow!,
              style: const TextStyle(
                  fontSize: 13, fontWeight: FontWeight.w600, color: AppColors.primary)),
          const SizedBox(height: 10),
        ],
        Text(title,
            style: TextStyle(
                fontSize: size,
                fontWeight: FontWeight.w700,
                height: 1.15,
                letterSpacing: -0.4,
                color: AppColors.text)),
        if (subtitle != null) ...[
          const SizedBox(height: 10),
          Text(subtitle!,
              style: const TextStyle(fontSize: 15, height: 1.45, color: AppColors.textMuted)),
        ],
      ],
    );
  }
}

/// Columna desplazable que mantiene el botón principal al fondo.
class BottomPinnedScroll extends StatelessWidget {
  const BottomPinnedScroll({
    super.key,
    required this.children,
    required this.bottom,
    this.padding = const EdgeInsets.fromLTRB(24, 24, 24, 24),
  });

  final List<Widget> children;
  final List<Widget> bottom;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(builder: (context, constraints) {
      return SingleChildScrollView(
        padding: padding,
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: constraints.maxHeight - padding.vertical),
          child: IntrinsicHeight(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                ...children,
                const Spacer(),
                const SizedBox(height: 20),
                ...bottom,
              ],
            ),
          ),
        ),
      );
    });
  }
}
