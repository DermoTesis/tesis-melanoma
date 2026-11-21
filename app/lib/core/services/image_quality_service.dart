import 'dart:io';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:image/image.dart' as img;

/// Control local de la calidad técnica de cada imagen (RF-02.2, RNF-16).
///
/// Heurísticas de resolución, formato, luminancia media (iluminación) y
/// varianza del Laplaciano (enfoque). Se mantienen como control definitivo,
/// sin un modelo TFLite (D3 de PENDIENTES.md), pero sus cortes **no están
/// validados**: no se contrastaron con el modelo ni con las degradaciones de
/// EXP-10. La clasificación de la lesión se ejecuta siempre en el backend.
class ImageQualityService {
  const ImageQualityService();

  static const minSide = 1024;
  static const minLuminance = 55.0;
  static const maxLuminance = 228.0;

  /// Umbral conservador de nitidez sobre la imagen reducida a 512 px.
  static const minSharpness = 18.0;
  static const analysisWidth = 512;

  Future<ImageQualityReport> analyzeFile(String path) async {
    final bytes = await File(path).readAsBytes();
    final header = inspectHeader(bytes);
    if (!header.formatOk || header.width == null) {
      return ImageQualityReport.fromParts(header: header);
    }
    final pixels = await _decodeDownscaled(bytes);
    if (pixels == null) return ImageQualityReport.fromParts(header: header);
    final metrics = await compute(_metricsIsolate, pixels);
    return ImageQualityReport.fromParts(header: header, metrics: metrics);
  }

  /// Decodifica con el decodificador nativo a un ancho reducido.
  Future<RgbaPixels?> _decodeDownscaled(Uint8List bytes) async {
    try {
      final codec = await ui.instantiateImageCodec(bytes, targetWidth: analysisWidth);
      final frame = await codec.getNextFrame();
      final data = await frame.image.toByteData(format: ui.ImageByteFormat.rawRgba);
      final result = data == null
          ? null
          : RgbaPixels(data.buffer.asUint8List(), frame.image.width, frame.image.height);
      frame.image.dispose();
      codec.dispose();
      return result;
    } catch (_) {
      return null;
    }
  }

  /// Lee formato y dimensiones sin decodificar toda la imagen.
  static ImageHeader inspectHeader(Uint8List bytes) {
    final format = detectFormat(bytes);
    if (format != ImageFormatKind.jpg && format != ImageFormatKind.png) {
      return ImageHeader(format: format);
    }
    try {
      final decoder = img.findDecoderForData(bytes);
      final info = decoder?.startDecode(bytes);
      return ImageHeader(format: format, width: info?.width, height: info?.height);
    } catch (_) {
      return ImageHeader(format: format);
    }
  }

  static ImageFormatKind detectFormat(Uint8List b) {
    if (b.length >= 3 && b[0] == 0xFF && b[1] == 0xD8 && b[2] == 0xFF) {
      return ImageFormatKind.jpg;
    }
    if (b.length >= 4 && b[0] == 0x89 && b[1] == 0x50 && b[2] == 0x4E && b[3] == 0x47) {
      return ImageFormatKind.png;
    }
    if (b.length >= 12) {
      final brand = String.fromCharCodes(b.sublist(4, 12));
      if (brand.startsWith('ftyphei') ||
          brand.startsWith('ftypheix') ||
          brand.startsWith('ftypmif1') ||
          brand.startsWith('ftyphevc')) {
        return ImageFormatKind.heic;
      }
    }
    return ImageFormatKind.otro;
  }

  /// Luminancia media (0–255) y varianza del Laplaciano en escala de grises.
  static PixelMetrics computeMetrics(RgbaPixels p) {
    final w = p.width, h = p.height;
    final gray = Float64List(w * h);
    double sum = 0;
    for (var i = 0, j = 0; i < gray.length; i++, j += 4) {
      final y = 0.299 * p.data[j] + 0.587 * p.data[j + 1] + 0.114 * p.data[j + 2];
      gray[i] = y;
      sum += y;
    }
    final mean = sum / gray.length;

    double lapSum = 0, lapSq = 0;
    var n = 0;
    for (var y = 1; y < h - 1; y++) {
      for (var x = 1; x < w - 1; x++) {
        final i = y * w + x;
        final lap = 4 * gray[i] - gray[i - 1] - gray[i + 1] - gray[i - w] - gray[i + w];
        lapSum += lap;
        lapSq += lap * lap;
        n++;
      }
    }
    final lapMean = n == 0 ? 0.0 : lapSum / n;
    final variance = n == 0 ? 0.0 : math.max(0.0, lapSq / n - lapMean * lapMean);
    return PixelMetrics(meanLuminance: mean, sharpness: variance);
  }
}

PixelMetrics _metricsIsolate(RgbaPixels p) => ImageQualityService.computeMetrics(p);

enum ImageFormatKind { jpg, png, heic, otro }

extension ImageFormatLabel on ImageFormatKind {
  String get label => switch (this) {
        ImageFormatKind.jpg => 'JPG',
        ImageFormatKind.png => 'PNG',
        ImageFormatKind.heic => 'HEIC',
        ImageFormatKind.otro => 'Desconocido',
      };
}

class RgbaPixels {
  const RgbaPixels(this.data, this.width, this.height);
  final Uint8List data;
  final int width;
  final int height;
}

class ImageHeader {
  const ImageHeader({required this.format, this.width, this.height});
  final ImageFormatKind format;
  final int? width;
  final int? height;

  bool get formatOk => format == ImageFormatKind.jpg || format == ImageFormatKind.png;
}

class PixelMetrics {
  const PixelMetrics({required this.meanLuminance, required this.sharpness});
  final double meanLuminance;
  final double sharpness;
}

enum QualityAspect { formato, resolucion, iluminacion, enfoque }

class ImageQualityReport {
  const ImageQualityReport({
    required this.header,
    required this.formatOk,
    required this.resolutionOk,
    required this.lightOk,
    required this.focusOk,
    this.metrics,
  });

  factory ImageQualityReport.fromParts({required ImageHeader header, PixelMetrics? metrics}) {
    final w = header.width, h = header.height;
    final resolutionOk = w != null &&
        h != null &&
        math.min(w, h) >= ImageQualityService.minSide;
    return ImageQualityReport(
      header: header,
      formatOk: header.formatOk,
      resolutionOk: resolutionOk,
      lightOk: metrics != null &&
          metrics.meanLuminance >= ImageQualityService.minLuminance &&
          metrics.meanLuminance <= ImageQualityService.maxLuminance,
      focusOk: metrics != null && metrics.sharpness >= ImageQualityService.minSharpness,
      metrics: metrics,
    );
  }

  final ImageHeader header;
  final bool formatOk;
  final bool resolutionOk;
  final bool lightOk;
  final bool focusOk;
  final PixelMetrics? metrics;

  bool get isApt => formatOk && resolutionOk && lightOk && focusOk;

  String get resolutionLabel => header.width == null
      ? 'No disponible'
      : '${header.width}×${header.height}';

  bool get tooBright =>
      metrics != null && metrics!.meanLuminance > ImageQualityService.maxLuminance;

  /// Indicación concreta para repetir la toma.
  String get guidance {
    if (!formatOk) return 'Formato ${header.format.label} no admitido. Usa una imagen JPG o PNG.';
    if (!resolutionOk) {
      return 'Resolución insuficiente ($resolutionLabel). Mínimo '
          '${ImageQualityService.minSide}×${ImageQualityService.minSide}.';
    }
    if (!lightOk) {
      return tooBright
          ? 'Repite esta toma. La imagen está sobreexpuesta: reduce la luz o desactiva el flash.'
          : 'Repite esta toma. Acerca una fuente de luz o activa el flash.';
    }
    if (!focusOk) {
      return 'Repite esta toma. La imagen está desenfocada: mantén el teléfono estable y toca para enfocar.';
    }
    return 'Toma apta para el análisis.';
  }
}
