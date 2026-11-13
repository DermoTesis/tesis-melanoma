import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/services/image_quality_service.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/common.dart';
import '../../domain/models/clinical_case.dart';
import '../../providers/case_providers.dart';
import 'capture_widgets.dart';

/// Pantallas 10 y 11 · Captura guiada de la foto panorámica y la de
/// acercamiento (HU08, HU09, RF-02.1, RF-02.2, RNF-16).
class CameraCaptureScreen extends ConsumerStatefulWidget {
  const CameraCaptureScreen({super.key, required this.patientId});
  final String patientId;

  @override
  ConsumerState<CameraCaptureScreen> createState() => _CameraCaptureScreenState();
}

class _CameraCaptureScreenState extends ConsumerState<CameraCaptureScreen>
    with WidgetsBindingObserver {
  final _quality = const ImageQualityService();
  CameraController? _controller;
  String? _cameraError;
  bool _initializing = true;
  bool _busy = false;
  bool _torch = false;
  ImageView _step = ImageView.panoramica;
  ImageQualityReport? _lastReport;
  ImageView? _reportView;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    final draft = ref.read(captureDraftProvider);
    if (draft == null || draft.patientId != widget.patientId) {
      Future.microtask(
          () => ref.read(captureDraftProvider.notifier).start(widget.patientId));
    } else if (draft.panoramica != null) {
      _step = ImageView.acercamiento;
    }
    _initCamera();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller?.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final c = _controller;
    if (c == null || !c.value.isInitialized) return;
    if (state == AppLifecycleState.inactive) {
      c.dispose();
      _controller = null;
      if (mounted) setState(() {});
    } else if (state == AppLifecycleState.resumed) {
      _initCamera();
    }
  }

  Future<void> _initCamera() async {
    setState(() {
      _initializing = true;
      _cameraError = null;
    });
    try {
      final cameras = await availableCameras();
      if (cameras.isEmpty) throw CameraException('no-camera', 'Sin cámaras');
      final back = cameras.firstWhere(
        (c) => c.lensDirection == CameraLensDirection.back,
        orElse: () => cameras.first,
      );
      final controller = CameraController(
        back,
        ResolutionPreset.veryHigh,
        enableAudio: false,
        imageFormatGroup: ImageFormatGroup.jpeg,
      );
      await controller.initialize();
      await controller.setFlashMode(FlashMode.off);
      if (!mounted) {
        await controller.dispose();
        return;
      }
      setState(() {
        _controller = controller;
        _torch = false;
      });
    } on CameraException catch (e) {
      setState(() => _cameraError = e.code == 'CameraAccessDenied'
          ? 'Se necesita permiso de cámara para capturar la lesión. Actívalo en los ajustes '
              'del teléfono o carga las imágenes desde la galería.'
          : 'No se pudo iniciar la cámara (${e.description ?? e.code}). '
              'Puedes cargar las imágenes desde la galería.');
    } finally {
      if (mounted) setState(() => _initializing = false);
    }
  }

  Future<void> _toggleTorch() async {
    final c = _controller;
    if (c == null) return;
    final next = !_torch;
    try {
      await c.setFlashMode(next ? FlashMode.torch : FlashMode.off);
      setState(() => _torch = next);
    } on CameraException {
      if (mounted) showAppSnack(context, 'El flash no está disponible.', error: true);
    }
  }

  Future<void> _focusAt(TapUpDetails d, BoxConstraints box) async {
    final c = _controller;
    if (c == null) return;
    final p = Offset(d.localPosition.dx / box.maxWidth, d.localPosition.dy / box.maxHeight);
    try {
      await c.setFocusPoint(p);
      await c.setExposurePoint(p);
    } on CameraException {
      // Algunos dispositivos no admiten enfoque por punto.
    }
  }

  Future<void> _shoot() async {
    final c = _controller;
    if (c == null || !c.value.isInitialized || _busy) return;
    setState(() => _busy = true);
    try {
      final file = await c.takePicture();
      final report = await _quality.analyzeFile(file.path);
      if (!mounted) return;
      final view = _step;
      setState(() {
        _lastReport = report;
        _reportView = view;
      });
      if (!report.isApt) return;
      final draft = ref.read(captureDraftProvider);
      ref.read(captureDraftProvider.notifier).setImage(CaseImage(
            view: view,
            source: CaptureSource.camara,
            conDermatoscopio: draft?.conDermatoscopio ?? true,
            localPath: file.path,
            width: report.header.width,
            height: report.header.height,
          ));
      if (view == ImageView.panoramica) {
        setState(() => _step = ImageView.acercamiento);
      } else {
        await _controller?.setFlashMode(FlashMode.off);
        if (mounted) {
          setState(() => _torch = false);
          context.push('/captura/${widget.patientId}/datos');
        }
      }
    } on CameraException catch (e) {
      if (mounted) showAppSnack(context, 'No se pudo tomar la foto: ${e.code}', error: true);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _retakePanoramic() {
    ref.read(captureDraftProvider.notifier).clearImage(ImageView.panoramica);
    setState(() {
      _step = ImageView.panoramica;
      _lastReport = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final draft = ref.watch(captureDraftProvider);
    final dermatoscope = draft?.conDermatoscopio ?? true;
    final report = _reportView == _step ? _lastReport : null;
    // Al volver de la pantalla de datos, la segunda foto ya existe.
    final panoramicDone = draft?.panoramica != null;

    return Scaffold(
      backgroundColor: AppColors.cameraBg,
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(6, 4, 12, 4),
              child: Row(
                children: [
                  IconButton(
                    icon: const Icon(Icons.close, color: Colors.white),
                    onPressed: () => context.pop(),
                  ),
                  const Spacer(),
                  DarkToggle(
                    options: const ['Con dermatoscopio', 'Sin'],
                    selected: dermatoscope ? 0 : 1,
                    onChanged: (i) =>
                        ref.read(captureDraftProvider.notifier).setDermatoscope(i == 0),
                  ),
                  const Spacer(),
                  TextButton.icon(
                    style: TextButton.styleFrom(foregroundColor: Colors.white),
                    onPressed: _controller == null ? null : _toggleTorch,
                    icon: Icon(_torch ? Icons.flash_on : Icons.flash_off, size: 18),
                    label: const Text('Flash'),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 18),
              child: CaptureSteps(current: _step, panoramicDone: panoramicDone),
            ),
            const SizedBox(height: 10),
            Expanded(child: _buildViewport(report)),
            const SizedBox(height: 8),
            SizedBox(
              height: 120,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceAround,
                children: [
                  _step == ImageView.acercamiento && draft?.panoramica != null
                      ? _SideButton(
                          label: 'Panorámica',
                          onTap: _retakePanoramic,
                          child: Container(
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(10),
                              border: Border.all(color: AppColors.successAccent, width: 2),
                            ),
                            child: LesionThumbnail(
                                path: draft!.panoramica!.localPath, size: 44, radius: 8),
                          ),
                        )
                      : _SideButton(
                          label: 'Galería',
                          onTap: () => context.push('/captura/${widget.patientId}/galeria'),
                          child: Container(
                            width: 44,
                            height: 44,
                            decoration: BoxDecoration(
                              color: Colors.white.withValues(alpha: 0.18),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: const Icon(Icons.photo_library_outlined, color: Colors.white),
                          ),
                        ),
                  ShutterButton(
                    enabled: _controller != null && !_busy,
                    busy: _busy,
                    onTap: _shoot,
                  ),
                  _SideButton(
                    label: 'Guía',
                    onTap: () => showCaptureGuide(context, _step),
                    child: const SizedBox(
                      width: 44,
                      height: 44,
                      child: Icon(Icons.help_outline, color: Colors.white70),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildViewport(ImageQualityReport? report) {
    final c = _controller;
    Widget background;
    if (_initializing) {
      background = const Center(child: CircularProgressIndicator(color: Colors.white));
    } else if (_cameraError != null || c == null || !c.value.isInitialized) {
      background = Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.no_photography_outlined, color: Colors.white70, size: 40),
              const SizedBox(height: 12),
              Text(_cameraError ?? 'Cámara no disponible.',
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white70, height: 1.4)),
              const SizedBox(height: 16),
              OutlinedButton(
                style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.white,
                  side: const BorderSide(color: Colors.white54),
                  minimumSize: const Size(160, 44),
                ),
                onPressed: _initCamera,
                child: const Text('Reintentar'),
              ),
            ],
          ),
        ),
      );
    } else {
      final ps = c.value.previewSize!;
      background = LayoutBuilder(
        builder: (context, box) => GestureDetector(
          onTapUp: (d) => _focusAt(d, box),
          child: ClipRect(
            child: FittedBox(
              fit: BoxFit.cover,
              child: SizedBox(width: ps.height, height: ps.width, child: CameraPreview(c)),
            ),
          ),
        ),
      );
    }

    return Stack(
      fit: StackFit.expand,
      children: [
        ColoredBox(color: const Color(0xFF3A2E27), child: background),
        IgnorePointer(child: Center(child: GuideFrame(view: _step))),
        Positioned(
          top: 12,
          left: 14,
          right: 14,
          child: QualityChips(view: _step, report: report, analyzing: _busy),
        ),
        if (report != null || _step == ImageView.acercamiento)
          Positioned(
            left: 16,
            right: 16,
            bottom: 14,
            child: CaptureFeedback(
              report: report,
              view: _step,
            ),
          ),
      ],
    );
  }
}

class _SideButton extends StatelessWidget {
  const _SideButton({required this.label, required this.onTap, required this.child});
  final String label;
  final VoidCallback onTap;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: SizedBox(
        width: 72,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            child,
            const SizedBox(height: 6),
            Text(label, style: AppFonts.mono(fontSize: 11, color: Colors.white)),
          ],
        ),
      ),
    );
  }
}
