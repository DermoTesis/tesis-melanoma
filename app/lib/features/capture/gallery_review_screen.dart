import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart' as picker;

import '../../core/services/image_quality_service.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/common.dart';
import '../../domain/models/clinical_case.dart';
import '../../providers/case_providers.dart';
import '../auth/auth_widgets.dart';

/// Pantalla 12 · Imágenes de galería, validadas por separado (HU10, RF-02.2).
class GalleryReviewScreen extends ConsumerStatefulWidget {
  const GalleryReviewScreen({super.key, required this.patientId});
  final String patientId;

  @override
  ConsumerState<GalleryReviewScreen> createState() => _GalleryReviewScreenState();
}

class _Pick {
  const _Pick(this.path, this.name, this.report);
  final String path;
  final String name;
  final ImageQualityReport report;
}

class _GalleryReviewScreenState extends ConsumerState<GalleryReviewScreen> {
  final _picker = picker.ImagePicker();
  final _quality = const ImageQualityService();
  final _picks = <ImageView, _Pick>{};
  ImageView? _analyzing;

  @override
  void initState() {
    super.initState();
    // Fuera del build: modificar un provider en initState no está permitido.
    Future.microtask(() => ref.read(captureDraftProvider.notifier).start(widget.patientId));
  }

  Future<void> _pick(ImageView view) async {
    final file = await _picker.pickImage(source: picker.ImageSource.gallery);
    if (file == null) return;
    setState(() => _analyzing = view);
    try {
      final report = await _quality.analyzeFile(file.path);
      if (!mounted) return;
      setState(() => _picks[view] = _Pick(file.path, file.name, report));
      final notifier = ref.read(captureDraftProvider.notifier);
      if (report.isApt) {
        notifier.setImage(CaseImage(
          view: view,
          source: CaptureSource.galeria,
          conDermatoscopio: ref.read(captureDraftProvider)?.conDermatoscopio ?? true,
          localPath: file.path,
          width: report.header.width,
          height: report.header.height,
        ));
      } else {
        notifier.clearImage(view);
      }
    } finally {
      if (mounted) setState(() => _analyzing = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final draft = ref.watch(captureDraftProvider);
    final apt = [draft?.panoramica, draft?.acercamiento].where((i) => i != null).length;
    final rejected = ImageView.values
        .firstWhere((v) => _picks[v] != null && !_picks[v]!.report.isApt, orElse: () => ImageView.panoramica);
    final hasRejected = _picks.values.any((p) => !p.report.isApt);

    return Scaffold(
      appBar: AppBar(title: const Text('Imágenes de galería')),
      body: SafeArea(
        top: false,
        child: BottomPinnedScroll(
          padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
          children: [
            const Text(
              'Indica cuál es la panorámica y cuál el acercamiento. Ambas son obligatorias.',
              style: TextStyle(fontSize: 14, height: 1.45, color: AppColors.textMuted),
            ),
            const SizedBox(height: 14),
            for (final view in ImageView.values) ...[
              _Slot(
                view: view,
                image: view == ImageView.panoramica ? draft?.panoramica : draft?.acercamiento,
                pick: _picks[view],
                analyzing: _analyzing == view,
                onPick: () => _pick(view),
              ),
              const SizedBox(height: 12),
            ],
          ],
          bottom: [
            if (hasRejected) ...[
              PrimaryButton(
                label: 'Reemplazar ${rejected.label.toLowerCase()}',
                onPressed: () => _pick(rejected),
              ),
              const SizedBox(height: 10),
            ],
            PrimaryButton(
              label: apt == 2 ? 'Continuar' : 'Continuar · $apt de 2 aptas',
              onPressed: draft?.hasBothImages ?? false
                  ? () => context.push('/captura/${widget.patientId}/datos')
                  : null,
            ),
          ],
        ),
      ),
    );
  }
}

class _Slot extends StatelessWidget {
  const _Slot({
    required this.view,
    required this.image,
    required this.pick,
    required this.analyzing,
    required this.onPick,
  });

  final ImageView view;
  final CaseImage? image;
  final _Pick? pick;
  final bool analyzing;
  final VoidCallback onPick;

  @override
  Widget build(BuildContext context) {
    final report = pick?.report;
    final rejected = report != null && !report.isApt;
    final path = rejected ? pick!.path : image?.localPath;
    final hasImage = image != null || pick != null;
    final dims = report?.resolutionLabel ??
        (image?.width != null ? '${image!.width}×${image!.height}' : null);

    return AppCard(
      padding: const EdgeInsets.all(12),
      border: rejected ? Border.all(color: AppColors.errorBorder, width: 1.5) : null,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              hasImage
                  ? LesionThumbnail(path: path, size: 68, radius: 12, faded: rejected)
                  : Container(
                      width: 68,
                      height: 68,
                      decoration: BoxDecoration(
                          color: AppColors.surfaceMuted, borderRadius: BorderRadius.circular(12)),
                      child: const Icon(Icons.add_photo_alternate_outlined, color: AppColors.textSubtle),
                    ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SectionLabel(view.label.toUpperCase()),
                    const SizedBox(height: 3),
                    if (pick != null || dims != null)
                      Text(
                        [if (pick != null) pick!.name, ?dims].join(' · '),
                        overflow: TextOverflow.ellipsis,
                        style: AppFonts.mono(fontSize: 11),
                      ),
                    const SizedBox(height: 3),
                    if (analyzing)
                      const Text('Analizando calidad…',
                          style: TextStyle(fontSize: 13, color: AppColors.textSubtle))
                    else if (rejected)
                      const Text('No apta para análisis',
                          style: TextStyle(
                              fontSize: 13, fontWeight: FontWeight.w600, color: AppColors.errorText))
                    else if (image != null)
                      const Text('✓ Apta',
                          style: TextStyle(
                              fontSize: 13, fontWeight: FontWeight.w600, color: AppColors.primaryDark))
                    else
                      const Text('Sin imagen',
                          style: TextStyle(fontSize: 13, color: AppColors.textSubtle)),
                  ],
                ),
              ),
              TextButton(
                onPressed: analyzing ? null : onPick,
                child: Text(hasImage ? 'Cambiar' : 'Elegir'),
              ),
            ],
          ),
          if (rejected) ...[
            const Divider(height: 22, color: Color(0xFFF0DCD5)),
            _ReportRow('Resolución',
                report.resolutionOk ? 'Correcta' : '${report.resolutionLabel} · mín. 1024×1024',
                report.resolutionOk),
            _ReportRow(
                'Formato',
                report.formatOk ? report.header.format.label : '${report.header.format.label} · usa JPG o PNG',
                report.formatOk),
            if (report.formatOk && report.resolutionOk) ...[
              _ReportRow('Iluminación', report.lightOk ? 'Correcta' : (report.tooBright ? 'Sobreexpuesta' : 'Insuficiente'),
                  report.lightOk),
              _ReportRow('Enfoque', report.focusOk ? 'Correcto' : 'Desenfocada', report.focusOk),
            ],
          ],
        ],
      ),
    );
  }
}

class _ReportRow extends StatelessWidget {
  const _ReportRow(this.label, this.value, this.ok);
  final String label;
  final String value;
  final bool ok;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        children: [
          Text(label, style: const TextStyle(fontSize: 13, color: AppColors.textMuted)),
          const SizedBox(width: 8),
          Expanded(
            child: Text(value,
                textAlign: TextAlign.right,
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: ok ? AppColors.primaryDark : AppColors.errorText,
                )),
          ),
        ],
      ),
    );
  }
}
