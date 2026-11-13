import 'prediction.dart';

enum ValidationDecision { confirmar, corregir, descartar }

extension ValidationDecisionLabel on ValidationDecision {
  String get label {
    switch (this) {
      case ValidationDecision.confirmar:
        return 'Confirmar';
      case ValidationDecision.corregir:
        return 'Corregir';
      case ValidationDecision.descartar:
        return 'Descartar';
    }
  }

  String get pastLabel {
    switch (this) {
      case ValidationDecision.confirmar:
        return 'Confirmada';
      case ValidationDecision.corregir:
        return 'Corregida';
      case ValidationDecision.descartar:
        return 'Descartada';
    }
  }
}

/// Registro inmutable de la validación médica (RF-04.4, RNF-04).
/// Se almacena con permisos de solo inserción: los cambios posteriores se
/// registran como validaciones complementarias.
class ClinicalValidation {
  const ClinicalValidation({
    required this.id,
    required this.caseId,
    required this.uidEspecialista,
    required this.especialistaNombre,
    required this.cmp,
    required this.decision,
    required this.claseFinal,
    required this.sustentoClinico,
    required this.fechaValidacion,
    required this.prediccionOriginal,
    this.examenesAdicionales,
    this.sugerenciaTomada,
    this.complementaDe,
  });

  final String id;
  final String caseId;
  final String uidEspecialista;
  final String especialistaNombre;
  final String cmp;
  final ValidationDecision decision;

  /// Clasificación final del especialista. Nula si descarta la predicción.
  final LesionClass? claseFinal;
  final String sustentoClinico;
  final DateTime fechaValidacion;

  /// Copia de la predicción original, que nunca se sobrescribe (RF-04.2).
  final Prediction prediccionOriginal;
  final String? examenesAdicionales;

  /// Constancia de si la sugerencia de exámenes fue tomada (HU29).
  final bool? sugerenciaTomada;

  /// Id de la validación a la que complementa, si aplica.
  final String? complementaDe;

  bool get isComplementary => complementaDe != null;

  String get conclusionLabel {
    if (decision == ValidationDecision.descartar || claseFinal == null) {
      return 'Predicción descartada';
    }
    return '${decision.pastLabel}: ${claseFinal!.label.toLowerCase()}';
  }

  String get reportConclusion {
    if (claseFinal == null) {
      return 'Predicción preliminar descartada; se requiere evaluación clínica';
    }
    return claseFinal == LesionClass.maligno
        ? 'Lesión compatible con melanoma maligno'
        : 'Lesión compatible con proceso benigno';
  }
}
