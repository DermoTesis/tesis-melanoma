import 'dart:math';
import 'dart:typed_data';

import 'package:dermavia/core/services/image_quality_service.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;

RgbaPixels _pixels(int w, int h, int Function(int x, int y) value) {
  final data = Uint8List(w * h * 4);
  for (var y = 0; y < h; y++) {
    for (var x = 0; x < w; x++) {
      final v = value(x, y);
      final i = (y * w + x) * 4;
      data[i] = v;
      data[i + 1] = v;
      data[i + 2] = v;
      data[i + 3] = 255;
    }
  }
  return RgbaPixels(data, w, h);
}

void main() {
  test('detecta formatos por su firma', () {
    final jpg = img.encodeJpg(img.Image(width: 8, height: 8));
    final png = img.encodePng(img.Image(width: 8, height: 8));
    final heic = Uint8List.fromList([0, 0, 0, 24, ...'ftypheic'.codeUnits, 0, 0]);
    expect(ImageQualityService.detectFormat(jpg), ImageFormatKind.jpg);
    expect(ImageQualityService.detectFormat(png), ImageFormatKind.png);
    expect(ImageQualityService.detectFormat(heic), ImageFormatKind.heic);
  });

  test('lee las dimensiones sin decodificar toda la imagen', () {
    final small = ImageQualityService.inspectHeader(
        img.encodeJpg(img.Image(width: 640, height: 480)));
    expect(small.width, 640);
    final report = ImageQualityReport.fromParts(header: small);
    expect(report.resolutionOk, isFalse);
    expect(report.guidance, contains('Resolución insuficiente'));
  });

  test('rechaza HEIC con un motivo claro', () {
    final heic = Uint8List.fromList([0, 0, 0, 24, ...'ftypheic'.codeUnits, 0, 0]);
    final report = ImageQualityReport.fromParts(header: ImageQualityService.inspectHeader(heic));
    expect(report.isApt, isFalse);
    expect(report.guidance, contains('JPG o PNG'));
  });

  group('métricas de píxeles', () {
    const header = ImageHeader(format: ImageFormatKind.jpg, width: 3024, height: 4032);
    final rnd = Random(7);

    test('imagen oscura → iluminación insuficiente', () {
      final m = ImageQualityService.computeMetrics(_pixels(64, 64, (_, _) => 15 + rnd.nextInt(30)));
      final r = ImageQualityReport.fromParts(header: header, metrics: m);
      expect(r.lightOk, isFalse);
      expect(r.guidance, contains('fuente de luz'));
    });

    test('imagen uniforme → desenfocada', () {
      final m = ImageQualityService.computeMetrics(_pixels(64, 64, (_, _) => 128));
      final r = ImageQualityReport.fromParts(header: header, metrics: m);
      expect(r.lightOk, isTrue);
      expect(r.focusOk, isFalse);
    });

    test('imagen con detalle e iluminación correcta → apta', () {
      final m = ImageQualityService.computeMetrics(
          _pixels(64, 64, (x, y) => ((x ~/ 2 + y ~/ 2) % 2 == 0) ? 90 : 170));
      final r = ImageQualityReport.fromParts(header: header, metrics: m);
      expect(r.isApt, isTrue);
    });
  });
}
