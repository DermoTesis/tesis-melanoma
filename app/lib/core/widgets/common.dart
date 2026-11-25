import 'dart:io';

import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../theme/app_theme.dart';

/// Botón principal de ancho completo (54 px, radio 14).
class PrimaryButton extends StatelessWidget {
  const PrimaryButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.loading = false,
    this.icon,
  });

  final String label;
  final VoidCallback? onPressed;
  final bool loading;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    return FilledButton(
      onPressed: loading ? null : onPressed,
      child: loading
          ? const SizedBox(
              width: 22,
              height: 22,
              child: CircularProgressIndicator(strokeWidth: 2.4, color: Colors.white),
            )
          : Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (icon != null) ...[Icon(icon, size: 20), const SizedBox(width: 8)],
                Flexible(child: Text(label, textAlign: TextAlign.center)),
              ],
            ),
    );
  }
}

class SecondaryButton extends StatelessWidget {
  const SecondaryButton({super.key, required this.label, required this.onPressed, this.icon});

  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    return OutlinedButton(
      onPressed: onPressed,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[Icon(icon, size: 20), const SizedBox(width: 8)],
          Flexible(child: Text(label, textAlign: TextAlign.center)),
        ],
      ),
    );
  }
}

/// Etiqueta superior de campo, como en los mockups.
class FieldLabel extends StatelessWidget {
  const FieldLabel(this.text, {super.key, this.error = false});
  final String text;
  final bool error;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Text(
        text,
        style: TextStyle(
          fontSize: 13,
          fontWeight: FontWeight.w600,
          color: error ? AppColors.error : AppColors.textMuted,
        ),
      ),
    );
  }
}

class AppTextField extends StatelessWidget {
  const AppTextField({
    super.key,
    required this.label,
    this.controller,
    this.hint,
    this.keyboardType,
    this.obscureText = false,
    this.validator,
    this.onChanged,
    this.suffix,
    this.mono = false,
    this.maxLines = 1,
    this.minLines,
    this.textCapitalization = TextCapitalization.none,
    this.autofillHints,
    this.readOnly = false,
    this.onTap,
    this.errorText,
    this.fillColor,
  });

  final String label;
  final TextEditingController? controller;
  final String? hint;
  final TextInputType? keyboardType;
  final bool obscureText;
  final String? Function(String?)? validator;
  final ValueChanged<String>? onChanged;
  final Widget? suffix;
  final bool mono;
  final int maxLines;
  final int? minLines;
  final TextCapitalization textCapitalization;
  final Iterable<String>? autofillHints;
  final bool readOnly;
  final VoidCallback? onTap;
  final String? errorText;
  final Color? fillColor;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        FieldLabel(label, error: errorText != null),
        TextFormField(
          controller: controller,
          keyboardType: keyboardType,
          obscureText: obscureText,
          validator: validator,
          onChanged: onChanged,
          maxLines: obscureText ? 1 : maxLines,
          minLines: minLines,
          readOnly: readOnly,
          onTap: onTap,
          textCapitalization: textCapitalization,
          autofillHints: autofillHints,
          style: mono
              ? AppFonts.mono(fontSize: 15, color: AppColors.text)
              : const TextStyle(fontSize: 16, color: AppColors.text),
          decoration: InputDecoration(
            hintText: hint,
            suffixIcon: suffix,
            errorText: errorText,
            fillColor: fillColor ?? (errorText != null ? AppColors.errorSurface : null),
          ),
        ),
      ],
    );
  }
}

/// Barra de progreso por pasos (activación, nuevo caso).
class StepProgress extends StatelessWidget {
  const StepProgress({super.key, required this.total, required this.current});
  final int total;
  final int current;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: List.generate(total, (i) {
        return Expanded(
          child: Container(
            height: 4,
            margin: EdgeInsets.only(right: i == total - 1 ? 0 : 6),
            decoration: BoxDecoration(
              color: i < current ? AppColors.primary : AppColors.border,
              borderRadius: BorderRadius.circular(2),
            ),
          ),
        );
      }),
    );
  }
}

enum BannerTone { error, warning, success, neutral }

class InfoBanner extends StatelessWidget {
  const InfoBanner({
    super.key,
    required this.message,
    this.tone = BannerTone.neutral,
    this.title,
    this.leading,
    this.trailing,
    this.onTap,
  });

  final String message;
  final BannerTone tone;
  final String? title;
  final Widget? leading;
  final Widget? trailing;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final (bg, fg) = switch (tone) {
      BannerTone.error => (AppColors.errorBg, AppColors.errorText),
      BannerTone.warning => (AppColors.warningBg, AppColors.warningText),
      BannerTone.success => (AppColors.successBg, AppColors.primaryDark),
      BannerTone.neutral => (AppColors.surfaceMuted, AppColors.textMuted),
    };
    final content = Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(12)),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (leading != null) ...[leading!, const SizedBox(width: 10)],
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (title != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Text(title!,
                        style: TextStyle(color: fg, fontWeight: FontWeight.w700, fontSize: 14)),
                  ),
                Text(message, style: TextStyle(color: fg, fontSize: 14, height: 1.4)),
              ],
            ),
          ),
          if (trailing != null) ...[const SizedBox(width: 8), trailing!],
        ],
      ),
    );
    return onTap == null
        ? content
        : Material(
            color: Colors.transparent,
            child: InkWell(
                borderRadius: BorderRadius.circular(12), onTap: onTap, child: content),
          );
  }
}

/// Círculo con signo de exclamación usado en los banners de error.
class AlertDot extends StatelessWidget {
  const AlertDot({super.key, this.text = '!', this.color = AppColors.error, this.size = 18});
  final String text;
  final Color color;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
      child: Text(text,
          style: TextStyle(
              color: Colors.white, fontSize: size * 0.62, fontWeight: FontWeight.w700)),
    );
  }
}

enum ChipTone { error, warning, success, solid, neutral }

/// Etiqueta pequeña de estado ("52 h", "Pendiente", "Validado").
class StatusChip extends StatelessWidget {
  const StatusChip(this.label, {super.key, this.tone = ChipTone.neutral});
  final String label;
  final ChipTone tone;

  @override
  Widget build(BuildContext context) {
    final (bg, fg) = switch (tone) {
      ChipTone.error => (AppColors.errorChip, AppColors.errorText),
      ChipTone.warning => (AppColors.warningChip, AppColors.warningText),
      ChipTone.success => (AppColors.successBg, AppColors.primaryDark),
      ChipTone.solid => (AppColors.primary, Colors.white),
      ChipTone.neutral => (AppColors.surfaceMuted, AppColors.textMuted),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(6)),
      child: Text(label,
          style: TextStyle(color: fg, fontSize: 11, fontWeight: FontWeight.w700)),
    );
  }
}

/// Tarjeta blanca con radio 16.
class AppCard extends StatelessWidget {
  const AppCard({
    super.key,
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.color = Colors.white,
    this.border,
    this.onTap,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;
  final Color color;
  final BoxBorder? border;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final box = Ink(
      decoration: BoxDecoration(
          color: color, borderRadius: BorderRadius.circular(16), border: border),
      child: Padding(padding: padding, child: child),
    );
    return Material(
      color: Colors.transparent,
      child: onTap == null
          ? box
          : InkWell(borderRadius: BorderRadius.circular(16), onTap: onTap, child: box),
    );
  }
}

/// Imagen de la lesión (archivo local o URL firmada del backend) o, si no
/// hay ninguna, el patrón rayado de los mockups.
class LesionThumbnail extends StatelessWidget {
  const LesionThumbnail({
    super.key,
    this.path,
    this.url,
    this.size,
    this.height,
    this.radius = 10,
    this.label,
    this.dark = false,
    this.faded = false,
  });

  final String? path;

  /// URL de lectura; se usa si no existe el archivo local.
  final String? url;
  final double? size;
  final double? height;
  final double radius;
  final String? label;
  final bool dark;
  final bool faded;

  @override
  Widget build(BuildContext context) {
    final file = path == null ? null : File(path!);
    final hasFile = file != null && file.existsSync();
    final placeholder = CustomPaint(
      painter: _StripePainter(
        dark ? AppColors.lesionDarkA : AppColors.lesionA,
        dark ? AppColors.lesionDarkB : AppColors.lesionB,
        dark ? 8 : 5,
      ),
      child: const SizedBox.expand(),
    );
    Widget child = hasFile
        ? Image.file(file, fit: BoxFit.cover, width: double.infinity, height: double.infinity)
        : url != null
            ? Image.network(url!,
                fit: BoxFit.cover,
                width: double.infinity,
                height: double.infinity,
                errorBuilder: (_, _, _) => placeholder)
            : placeholder;
    if (faded) child = Opacity(opacity: 0.55, child: child);
    return SizedBox(
      width: size,
      height: height ?? size,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(radius),
        child: Stack(
          fit: StackFit.expand,
          children: [
            child,
            if (label != null)
              Positioned(
                left: 8,
                bottom: 8,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.85),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(label!,
                      style: AppFonts.mono(fontSize: 10, color: AppColors.text)),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _StripePainter extends CustomPainter {
  _StripePainter(this.a, this.b, this.band);
  final Color a;
  final Color b;
  final double band;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Paint()..color = b);
    final paint = Paint()
      ..color = a
      ..strokeWidth = band;
    final step = band * 2 * 1.4142;
    for (double x = -size.height; x < size.width + size.height; x += step) {
      canvas.drawLine(Offset(x, size.height), Offset(x + size.height, 0), paint);
    }
  }

  @override
  bool shouldRepaint(covariant _StripePainter old) =>
      old.a != a || old.b != b || old.band != band;
}

class InitialsAvatar extends StatelessWidget {
  const InitialsAvatar(this.initials, {super.key, this.size = 40});
  final String initials;
  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      alignment: Alignment.center,
      decoration: const BoxDecoration(color: AppColors.primarySoft, shape: BoxShape.circle),
      child: Text(initials,
          style: TextStyle(
              color: AppColors.primaryDark,
              fontWeight: FontWeight.w700,
              fontSize: size * 0.34)),
    );
  }
}

/// Selector segmentado gris con opción blanca (sexo, decisión médica).
class SegmentedSelector<T> extends StatelessWidget {
  const SegmentedSelector({
    super.key,
    required this.options,
    required this.selected,
    required this.onChanged,
    required this.labelOf,
    this.solidSelection = false,
  });

  final List<T> options;
  final T? selected;
  final ValueChanged<T> onChanged;
  final String Function(T) labelOf;

  /// Selección en verde sólido (decisión médica, pantalla 17).
  final bool solidSelection;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(color: AppColors.canvas, borderRadius: BorderRadius.circular(12)),
      child: Row(
        children: [
          for (final o in options)
            Expanded(
              child: GestureDetector(
                onTap: () => onChanged(o),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 150),
                  height: 42,
                  margin: const EdgeInsets.symmetric(horizontal: 2),
                  alignment: Alignment.center,
                  decoration: BoxDecoration(
                    color: o == selected
                        ? (solidSelection ? AppColors.primary : Colors.white)
                        : Colors.transparent,
                    borderRadius: BorderRadius.circular(9),
                    boxShadow: o == selected && !solidSelection
                        ? const [BoxShadow(color: Color(0x14000000), blurRadius: 2, offset: Offset(0, 1))]
                        : null,
                  ),
                  child: Text(
                    labelOf(o),
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: o == selected ? FontWeight.w600 : FontWeight.w500,
                      color: o == selected && solidSelection
                          ? Colors.white
                          : AppColors.text,
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// Chip seleccionable con forma de píldora (síntomas, tiempo de aparición).
class PillChip extends StatelessWidget {
  const PillChip({
    super.key,
    required this.label,
    required this.selected,
    required this.onTap,
    this.outlined = true,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;
  final bool outlined;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 120),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        decoration: BoxDecoration(
          color: selected ? AppColors.primary : Colors.white,
          borderRadius: BorderRadius.circular(999),
          border: selected || !outlined ? null : Border.all(color: AppColors.border),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 13,
            fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
            color: selected ? Colors.white : AppColors.textBody,
          ),
        ),
      ),
    );
  }
}

/// Fila "Etiqueta ........ valor".
class KeyValueRow extends StatelessWidget {
  const KeyValueRow(this.label, this.value,
      {super.key, this.mono = false, this.bold = false, this.valueColor});
  final String label;
  final String value;
  final bool mono;
  final bool bold;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(fontSize: 13, color: AppColors.textSubtle)),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              value,
              textAlign: TextAlign.right,
              style: mono
                  ? AppFonts.mono(fontSize: 12, color: valueColor ?? AppColors.text)
                  : TextStyle(
                      fontSize: 13,
                      color: valueColor ?? AppColors.text,
                      fontWeight: bold ? FontWeight.w600 : FontWeight.w400),
            ),
          ),
        ],
      ),
    );
  }
}

/// Requisito con check (política de contraseña, consentimiento).
class CheckLine extends StatelessWidget {
  const CheckLine({super.key, required this.text, required this.ok, this.onTap});
  final String text;
  final bool ok;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            AnimatedContainer(
              duration: const Duration(milliseconds: 120),
              width: 20,
              height: 20,
              margin: const EdgeInsets.only(top: 1),
              decoration: BoxDecoration(
                color: ok ? AppColors.primary : Colors.white,
                borderRadius: BorderRadius.circular(onTap == null ? 10 : 6),
                border: ok ? null : Border.all(color: AppColors.textDisabled, width: 1.5),
              ),
              child: ok ? const Icon(Icons.check, size: 14, color: Colors.white) : null,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(text,
                  style: const TextStyle(fontSize: 14, height: 1.45, color: AppColors.textBody)),
            ),
          ],
        ),
      ),
    );
  }
}

/// Borde discontinuo (predicción preliminar no validada).
class DashedBorderBox extends StatelessWidget {
  const DashedBorderBox({
    super.key,
    required this.child,
    this.color = AppColors.warningAccent,
    this.radius = 16,
    this.padding = const EdgeInsets.all(14),
    this.background = Colors.white,
  });

  final Widget child;
  final Color color;
  final double radius;
  final EdgeInsetsGeometry padding;
  final Color background;

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      painter: _DashedPainter(color, radius),
      child: Container(
        padding: padding,
        decoration: BoxDecoration(color: background, borderRadius: BorderRadius.circular(radius)),
        child: child,
      ),
    );
  }
}

class _DashedPainter extends CustomPainter {
  _DashedPainter(this.color, this.radius);
  final Color color;
  final double radius;

  @override
  void paint(Canvas canvas, Size size) {
    final rrect = RRect.fromRectAndRadius(
        (Offset.zero & size).deflate(0.75), Radius.circular(radius));
    final path = Path()..addRRect(rrect);
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;
    for (final metric in path.computeMetrics()) {
      double d = 0;
      while (d < metric.length) {
        canvas.drawPath(metric.extractPath(d, d + 6), paint);
        d += 10;
      }
    }
  }

  @override
  bool shouldRepaint(covariant _DashedPainter old) => old.color != color;
}

/// Encabezado de sección dentro de una pantalla.
class SectionLabel extends StatelessWidget {
  const SectionLabel(this.text, {super.key, this.color = AppColors.textMuted});
  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Text(text,
        style: TextStyle(
            fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 0.6, color: color));
  }
}

class LoadingView extends StatelessWidget {
  const LoadingView({super.key});
  @override
  Widget build(BuildContext context) => const Center(child: CircularProgressIndicator());
}

class ErrorView extends StatelessWidget {
  const ErrorView(this.message, {super.key});
  final String message;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: InfoBanner(
            message: message,
            tone: BannerTone.error,
            leading: const AlertDot(),
          ),
        ),
      );
}

void showAppSnack(BuildContext context, String message, {bool error = false}) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(
      content: Text(message),
      backgroundColor: error ? AppColors.error : AppColors.ink,
    ));
}
