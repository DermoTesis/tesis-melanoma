/// Informe del caso cerrado (RF-05.2). Solo existe para casos CERRADOS.
class CaseReport {
  const CaseReport({
    required this.id,
    required this.caseId,
    required this.conductaClinica,
    required this.fechaCierre,
    required this.validationId,
  });

  final String id;
  final String caseId;

  /// Conducta o recomendación clínica (RF-05.4). La app no agenda citas.
  final String conductaClinica;
  final DateTime fechaCierre;

  /// Validación que habilitó el cierre (RF-07.1).
  final String validationId;
}

/// Datos que se incluyen en el PDF exportable. Construido explícitamente
/// para excluir las observaciones internas y la predicción sin validar
/// (RF-05.5).
class ReportDocument {
  const ReportDocument({
    required this.caseId,
    required this.fechaCierre,
    required this.pacienteNombre,
    required this.historiaClinica,
    required this.ubicacionLesion,
    required this.conclusion,
    required this.conducta,
    required this.especialistaNombre,
    required this.cmp,
    required this.establecimiento,
    required this.alcance,
    required this.constanciaHerramienta,
    this.foto1Path,
    this.foto2Path,
    this.fechaNacimiento,
    this.decision,
    this.sustentoClinico,
    this.examenesAdicionales,
  });

  final String caseId;
  final DateTime fechaCierre;
  final String pacienteNombre;
  final String historiaClinica;
  final String ubicacionLesion;
  final String conclusion;
  final String conducta;
  final String especialistaNombre;
  final String cmp;
  final String establecimiento;

  /// Nota de alcance de apoyo diagnóstico, obligatoria en todo informe.
  final String alcance;

  /// Constancia de que el caso se evaluó con apoyo de Dermavía y con qué
  /// versión (D5). No incluye la predicción preliminar (RF-05.5).
  final String constanciaHerramienta;
  final String? foto1Path;
  final String? foto2Path;

  // Campos que agrega el backend (`DocumentoInformeOut`).
  final DateTime? fechaNacimiento;
  final String? decision;
  final String? sustentoClinico;
  final String? examenesAdicionales;
}

/// Constancia de uso de la herramienta (D5). Mismo texto que
/// `informes.constancia_herramienta` del backend.
String toolUsageNotice(String? versionModelo) {
  final version = versionModelo == null ? '' : ' (versión $versionModelo)';
  return 'Caso evaluado con apoyo de Dermavía$version, herramienta de apoyo diagnóstico '
      'para melanoma. Su predicción preliminar fue revisada por el especialista, a quien '
      'corresponde la conclusión.';
}

const kScopeNotice =
    'Herramienta de apoyo diagnóstico. No reemplaza el criterio médico ni los '
    'exámenes clínicos pertinentes.';
