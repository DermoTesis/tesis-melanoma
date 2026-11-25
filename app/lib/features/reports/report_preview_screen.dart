import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:printing/printing.dart';

import '../../core/utils/formatters.dart';
import '../../core/errors/app_exception.dart';
import '../../core/theme/app_colors.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/navigation.dart';
import '../../core/widgets/common.dart';
import '../../domain/models/report.dart';
import '../../providers/repository_providers.dart';
import 'report_pdf.dart';

final _reportDocumentProvider = FutureProvider.autoDispose.family<ReportDocument, String>(
    (ref, caseId) => ref.watch(reportRepositoryProvider).buildReportDocument(caseId));

/// Pantalla 19 · Informe PDF del caso validado (HU27, RF-05.5).
class ReportPreviewScreen extends ConsumerWidget {
  const ReportPreviewScreen({super.key, required this.caseId});
  final String caseId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final docAsync = ref.watch(_reportDocumentProvider(caseId));
    return Scaffold(
      backgroundColor: const Color(0xFFDFE7E2),
      appBar: AppBar(
        leading: const SmartBackButton(),
        title: const Text('Informe'),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 16),
            child: Center(child: Text('PDF · 1 pág.', style: AppFonts.mono(fontSize: 12))),
          ),
        ],
      ),
      body: docAsync.when(
        loading: () => const LoadingView(),
        error: (e, _) => ErrorView(e is AppException ? e.message : '$e'),
        data: (doc) => Column(
          children: [
            Expanded(
              child: PdfPreview(
                build: (format) => buildReportPdf(doc, format: format),
                pdfFileName: 'Informe_${Fmt.caseId(doc.caseId)}.pdf',
                canChangeOrientation: false,
                canChangePageFormat: false,
                canDebug: false,
                allowPrinting: false,
                allowSharing: false,
                useActions: false,
                maxPageWidth: 520,
                scrollViewDecoration: const BoxDecoration(color: Color(0xFFDFE7E2)),
              ),
            ),
            Container(
              color: Colors.white,
              padding: const EdgeInsets.fromLTRB(18, 12, 18, 18),
              child: SafeArea(
                top: false,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Text('Excluye observaciones internas y la predicción sin validar.',
                        style: TextStyle(fontSize: 12, color: AppColors.textSubtle)),
                    const SizedBox(height: 10),
                    Row(
                      children: [
                        Expanded(
                          child: SecondaryButton(
                            label: 'Imprimir',
                            icon: Icons.print_outlined,
                            onPressed: () => Printing.layoutPdf(
                              name: 'Informe_${Fmt.caseId(doc.caseId)}',
                              onLayout: (format) => buildReportPdf(doc, format: format),
                            ),
                          ),
                        ),
                        const SizedBox(width: 10),
                        Expanded(
                          child: PrimaryButton(
                            label: 'Compartir',
                            icon: Icons.share_outlined,
                            onPressed: () async {
                              final bytes = await buildReportPdf(doc);
                              await Printing.sharePdf(
                                  bytes: bytes, filename: 'Informe_${Fmt.caseId(doc.caseId)}.pdf');
                            },
                          ),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
