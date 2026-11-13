import 'package:flutter/material.dart';

import '../../core/services/image_quality_service.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../domain/models/clinical_case.dart';

/// Conmutador oscuro "Con dermatoscopio / Sin".
class DarkToggle extends StatelessWidget {
  const DarkToggle({super.key, required this.options, required this.selected, required this.onChanged});
  final List<String> options;
  final int selected;
  final ValueChanged<int> onChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(3),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 0; i < options.length; i++)
            GestureDetector(
              onTap: () => onChanged(i),
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: i == selected ? Colors.white : Colors.transparent,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text(options[i],
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: i == selected ? AppColors.text : Colors.white,
                    )),
              ),
            ),
        ],
      ),
    );
  }
}

/// Indicador de pasos "1 · Panorámica / 2 · Acercamiento".
class CaptureSteps extends StatelessWidget {
  const CaptureSteps({super.key, required this.current, required this.panoramicDone});
  final ImageView current;
  final bool panoramicDone;

  @override
  Widget build(BuildContext context) {
    Widget step(String label, {required bool active, required bool done}) {
      final color = done
          ? const Color(0xFF8FD1B1)
          : active
              ? Colors.white
              : Colors.white.withValues(alpha: 0.5);
      return Expanded(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              height: 4,
              decoration: BoxDecoration(
                color: done
                    ? AppColors.successAccent
                    : active
                        ? Colors.white
                        : Colors.white.withValues(alpha: 0.4),
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            const SizedBox(height: 6),
            Text(label, style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w600)),
          ],
        ),
      );
    }

    final onPanoramic = current == ImageView.panoramica;
    return Row(
      children: [
        step(panoramicDone && !onPanoramic ? '✓ Panorámica' : '1 · Panorámica',
            active: onPanoramic, done: panoramicDone && !onPanoramic),
        const SizedBox(width: 8),
        step('2 · Acercamiento', active: !onPanoramic, done: false),
      ],
    );
  }
}

/// Marco guía: rectángulo para la panorámica, círculo para el acercamiento.
class GuideFrame extends StatelessWidget {
  const GuideFrame({super.key, required this.view});
  final ImageView view;

  @override
  Widget build(BuildContext context) {
    final panoramic = view == ImageView.panoramica;
    return CustomPaint(
      painter: _GuidePainter(circle: !panoramic),
      child: SizedBox(
        width: panoramic ? 240 : 220,
        height: panoramic ? 270 : 220,
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (panoramic)
                Container(
                  width: 34,
                  height: 34,
                  margin: const EdgeInsets.only(bottom: 10),
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(color: Colors.white, width: 2),
                  ),
                ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.45),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  panoramic ? 'lesión + zona corporal' : 'detalle de la lesión',
                  style: AppFonts.mono(fontSize: 11, color: Colors.white),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _GuidePainter extends CustomPainter {
  _GuidePainter({required this.circle});
  final bool circle;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.white.withValues(alpha: 0.85)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3;
    final path = Path();
    if (circle) {
      path.addOval(Offset.zero & size);
    } else {
      path.addRRect(RRect.fromRectAndRadius(Offset.zero & size, const Radius.circular(20)));
    }
    for (final m in path.computeMetrics()) {
      double d = 0;
      while (d < m.length) {
        canvas.drawPath(m.extractPath(d, d + 9), paint);
        d += 16;
      }
    }
  }

  @override
  bool shouldRepaint(covariant _GuidePainter old) => old.circle != circle;
}

/// Chips de enfoque, iluminación y distancia/resolución.
class QualityChips extends StatelessWidget {
  const QualityChips({super.key, required this.view, required this.report, required this.analyzing});
  final ImageView view;
  final ImageQualityReport? report;
  final bool analyzing;

  @override
  Widget build(BuildContext context) {
    final r = report;
    final items = <(String, bool?)>[
      ('Enfoque', r?.focusOk),
      (r != null && !r.lightOk ? (r.tooBright ? 'Sobreexpuesta' : 'Iluminación baja') : 'Iluminación',
          r?.lightOk),
      (view == ImageView.panoramica ? '~30 cm' : 'Distancia', r?.resolutionOk),
    ];
    if (analyzing) {
      return const Center(child: _Chip(label: 'Analizando calidad…', ok: null));
    }
    return Wrap(
      alignment: WrapAlignment.center,
      spacing: 6,
      runSpacing: 6,
      children: [for (final (label, ok) in items) _Chip(label: label, ok: ok)],
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip({required this.label, required this.ok});
  final String label;
  final bool? ok;

  @override
  Widget build(BuildContext context) {
    final color = switch (ok) {
      true => AppColors.primary.withValues(alpha: 0.92),
      false => AppColors.error.withValues(alpha: 0.95),
      null => Colors.black.withValues(alpha: 0.45),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(999)),
      child: Text(ok == true ? '✓ $label' : label,
          style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w600)),
    );
  }
}

/// Mensaje inferior de la captura (toma apta / repetir).
class CaptureFeedback extends StatelessWidget {
  const CaptureFeedback({super.key, required this.report, required this.view});
  final ImageQualityReport? report;
  final ImageView view;

  @override
  Widget build(BuildContext context) {
    final r = report;
    final bool ok;
    final String text;
    if (r == null) {
      ok = true;
      text = 'Panorámica guardada. Ahora acércate a la lesión para la foto de detalle.';
    } else if (r.isApt) {
      ok = true;
      text = view == ImageView.panoramica
          ? 'Toma apta. Incluye la lesión y referencias anatómicas cercanas para ubicarla.'
          : 'Toma apta.';
    } else {
      ok = false;
      text = view == ImageView.acercamiento
          ? '${r.guidance} La panorámica ya está guardada.'
          : r.guidance;
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(14)),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 20,
            height: 20,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: ok ? AppColors.primary : AppColors.error,
              shape: BoxShape.circle,
            ),
            child: Text(ok ? '✓' : '!',
                style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w700)),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(text,
                style: const TextStyle(fontSize: 13, height: 1.4, color: AppColors.text)),
          ),
        ],
      ),
    );
  }
}

class ShutterButton extends StatelessWidget {
  const ShutterButton({super.key, required this.enabled, required this.busy, required this.onTap});
  final bool enabled;
  final bool busy;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = enabled ? Colors.white : Colors.white.withValues(alpha: 0.4);
    return Semantics(
      button: true,
      label: 'Tomar foto',
      child: GestureDetector(
        onTap: enabled ? onTap : null,
        child: Container(
          width: 76,
          height: 76,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            border: Border.all(color: color, width: 4),
          ),
          child: busy
              ? const SizedBox(
                  width: 28,
                  height: 28,
                  child: CircularProgressIndicator(color: Colors.white, strokeWidth: 3))
              : Container(
                  width: 60,
                  height: 60,
                  decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                ),
        ),
      ),
    );
  }
}

void showCaptureGuide(BuildContext context, ImageView view) {
  final panoramic = view == ImageView.panoramica;
  final tips = panoramic
      ? const [
          'Encuadra la lesión junto con referencias anatómicas cercanas (~30 cm).',
          'Usa luz difusa y evita sombras sobre la piel.',
          'Toca la pantalla sobre la lesión para enfocar.',
        ]
      : const [
          'Acércate o apoya el dermatoscopio sobre la lesión.',
          'La lesión debe ocupar el círculo guía.',
          'Si la imagen sale oscura, activa el flash.',
        ];
  showModalBottomSheet<void>(
    context: context,
    backgroundColor: Colors.white,
    shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
    builder: (ctx) => SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(panoramic ? 'Foto 1 · Panorámica' : 'Foto 2 · Acercamiento',
                style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
            const SizedBox(height: 12),
            for (final t in tips)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('•  ', style: TextStyle(color: AppColors.primary)),
                    Expanded(child: Text(t, style: const TextStyle(height: 1.4))),
                  ],
                ),
              ),
            const SizedBox(height: 4),
            const Text(
              'La aplicación revisa enfoque, iluminación, formato y resolución (mín. 1024×1024). '
              'Las dos fotos son obligatorias.',
              style: TextStyle(fontSize: 13, color: AppColors.textSubtle, height: 1.4),
            ),
          ],
        ),
      ),
    ),
  );
}
