import 'dart:io';
import 'dart:typed_data';

import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;

import '../../core/utils/formatters.dart';
import '../../domain/models/clinical_case.dart';
import '../../domain/models/report.dart';

/// Genera el informe PDF del caso validado (HU27, RF-05.2, RF-05.3, RF-05.5).
/// Solo recibe un [ReportDocument], que por construcción no contiene las
/// observaciones internas ni la predicción sin validar.
Future<Uint8List> buildReportPdf(ReportDocument doc, {PdfPageFormat? format}) async {
  final pdf = pw.Document(
    title: 'Informe ${doc.caseId}',
    author: doc.especialistaNombre,
    creator: 'Dermavía',
  );

  Future<pw.ImageProvider?> loadImage(String? path) async {
    if (path == null) return null;
    final file = File(path);
    return await file.exists() ? pw.MemoryImage(await file.readAsBytes()) : null;
  }

  final panoramica = await loadImage(doc.panoramicaPath);
  final acercamiento = await loadImage(doc.acercamientoPath);

  const green = PdfColor.fromInt(0xFF1D6B4F);
  const greenDark = PdfColor.fromInt(0xFF14503A);
  const greenSoft = PdfColor.fromInt(0xFFE3F1EA);
  const muted = PdfColor.fromInt(0xFF5B6B63);
  const text = PdfColor.fromInt(0xFF13241C);
  const surface = PdfColor.fromInt(0xFFF4F8F5);
  const divider = PdfColor.fromInt(0xFFE2EBE6);

  pw.Widget kv(String k, String v) => pw.Padding(
        padding: const pw.EdgeInsets.only(bottom: 3),
        child: pw.Row(crossAxisAlignment: pw.CrossAxisAlignment.start, children: [
          pw.SizedBox(width: 90, child: pw.Text(k, style: const pw.TextStyle(color: muted, fontSize: 10))),
          pw.Expanded(child: pw.Text(v, style: const pw.TextStyle(color: text, fontSize: 10))),
        ]),
      );

  pw.Widget lesionImage(ImageView view, pw.ImageProvider? image) => pw.Expanded(
        child: pw.Column(crossAxisAlignment: pw.CrossAxisAlignment.start, children: [
          pw.Container(
            height: 200,
            width: double.infinity,
            decoration: pw.BoxDecoration(
              color: const PdfColor.fromInt(0xFFE7D7CC),
              borderRadius: pw.BorderRadius.circular(6),
            ),
            child: image == null
                ? pw.Center(
                    child: pw.Padding(
                      padding: const pw.EdgeInsets.all(8),
                      child: pw.Text('Imagen no disponible en este dispositivo',
                          textAlign: pw.TextAlign.center,
                          style: const pw.TextStyle(color: muted, fontSize: 9)),
                    ))
                : pw.ClipRRect(
                    horizontalRadius: 6,
                    verticalRadius: 6,
                    child: pw.Image(image, fit: pw.BoxFit.cover),
                  ),
          ),
          pw.SizedBox(height: 4),
          pw.Text(view.label, style: const pw.TextStyle(color: muted, fontSize: 9)),
        ]),
      );

  pdf.addPage(
    pw.Page(
      pageFormat: format ?? PdfPageFormat.a4,
      margin: const pw.EdgeInsets.all(40),
      build: (context) => pw.Column(
        crossAxisAlignment: pw.CrossAxisAlignment.start,
        children: [
          pw.Row(children: [
            pw.Text('Dermavia',
                style: pw.TextStyle(color: green, fontSize: 16, fontWeight: pw.FontWeight.bold)),
            pw.Spacer(),
            pw.Text('${doc.caseId} · ${Fmt.date(doc.fechaCierre)}',
                style: const pw.TextStyle(color: muted, fontSize: 10)),
          ]),
          pw.Divider(color: divider),
          pw.SizedBox(height: 8),
          pw.Text('Informe de caso validado',
              style: pw.TextStyle(color: text, fontSize: 20, fontWeight: pw.FontWeight.bold)),
          pw.SizedBox(height: 4),
          pw.Text(doc.establecimiento, style: const pw.TextStyle(color: muted, fontSize: 10)),
          pw.SizedBox(height: 14),
          kv('Paciente', '${doc.pacienteNombre} · ${doc.historiaClinica}'),
          kv('Lesión', doc.ubicacionLesion),
          kv('Fecha de cierre', Fmt.dateTime(doc.fechaCierre)),
          pw.SizedBox(height: 12),
          pw.Row(crossAxisAlignment: pw.CrossAxisAlignment.start, children: [
            lesionImage(ImageView.panoramica, panoramica),
            pw.SizedBox(width: 10),
            lesionImage(ImageView.acercamiento, acercamiento),
          ]),
          pw.SizedBox(height: 14),
          pw.Container(
            width: double.infinity,
            padding: const pw.EdgeInsets.all(12),
            decoration: pw.BoxDecoration(color: greenSoft, borderRadius: pw.BorderRadius.circular(6)),
            child: pw.Column(crossAxisAlignment: pw.CrossAxisAlignment.start, children: [
              pw.Text('CONCLUSIÓN VALIDADA POR EL ESPECIALISTA',
                  style: pw.TextStyle(color: greenDark, fontSize: 9, fontWeight: pw.FontWeight.bold)),
              pw.SizedBox(height: 4),
              pw.Text(doc.conclusion,
                  style: pw.TextStyle(color: text, fontSize: 13, fontWeight: pw.FontWeight.bold)),
            ]),
          ),
          pw.SizedBox(height: 12),
          pw.RichText(
            text: pw.TextSpan(children: [
              pw.TextSpan(
                  text: 'Conducta: ',
                  style: pw.TextStyle(fontWeight: pw.FontWeight.bold, fontSize: 11, color: text)),
              pw.TextSpan(text: doc.conducta, style: const pw.TextStyle(fontSize: 11, color: text)),
            ]),
          ),
          pw.SizedBox(height: 22),
          pw.Divider(color: divider),
          pw.Text(doc.especialistaNombre,
              style: pw.TextStyle(fontWeight: pw.FontWeight.bold, fontSize: 11, color: text)),
          pw.Text('Dermatología · CMP ${doc.cmp}', style: const pw.TextStyle(color: muted, fontSize: 10)),
          pw.Spacer(),
          pw.Container(
            width: double.infinity,
            padding: const pw.EdgeInsets.all(10),
            decoration: pw.BoxDecoration(color: surface, borderRadius: pw.BorderRadius.circular(6)),
            child: pw.Text(doc.alcance, style: const pw.TextStyle(color: muted, fontSize: 9)),
          ),
        ],
      ),
    ),
  );
  return pdf.save();
}
