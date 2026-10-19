enum LesionClass { benigno, maligno }

extension LesionClassLabel on LesionClass {
  String get label => this == LesionClass.benigno ? 'Benigno' : 'Maligno';
}

/// Nivel de confianza de la predicción preliminar, usado para sugerir
/// exámenes adicionales (RF-06.1).
enum PredictionConfidence { alta, ambigua, baja, benigna }

/// Predicción preliminar devuelta por el módulo Inferencia (RF-03.3).
/// Nunca es un diagnóstico: siempre requiere validación médica.
class Prediction {
  const Prediction({
    required this.probabilidadMalignidad,
    required this.clasePredicha,
    required this.versionModelo,
    required this.umbralOperativo,
    required this.fechaInferencia,
  });

  /// Probabilidad calibrada (regresión isotónica) de malignidad, 0..1.
  final double probabilidadMalignidad;
  final LesionClass clasePredicha;
  final String versionModelo;

  /// Umbral operativo sobre la probabilidad calibrada (EXP-04).
  final double umbralOperativo;
  final DateTime fechaInferencia;

  int get percent => (probabilidadMalignidad * 100).round();

  PredictionConfidence get confidence {
    final p = probabilidadMalignidad;
    if (clasePredicha == LesionClass.benigno) return PredictionConfidence.benigna;
    if (p >= 0.70) return PredictionConfidence.alta;
    if (p >= 0.30) return PredictionConfidence.ambigua;
    return PredictionConfidence.baja;
  }

  /// Sugerencia editable de exámenes adicionales cuando la confianza es
  /// baja o ambigua (RF-06.1). La decisión siempre es del especialista.
  String? get defaultSuggestion {
    switch (confidence) {
      case PredictionConfidence.ambigua:
        return 'Considerar dermatoscopia digital de seguimiento o biopsia '
            'para descartar un falso positivo antes de concluir.';
      case PredictionConfidence.baja:
        return 'Probabilidad apenas sobre el umbral operativo. Considerar '
            'control dermatoscópico en 3 meses o biopsia según hallazgos.';
      case PredictionConfidence.alta:
      case PredictionConfidence.benigna:
        return null;
    }
  }

  String get confidenceLabel {
    switch (confidence) {
      case PredictionConfidence.alta:
        return 'probabilidad alta';
      case PredictionConfidence.ambigua:
        return 'confianza ambigua';
      case PredictionConfidence.baja:
        return 'confianza baja';
      case PredictionConfidence.benigna:
        return 'preliminar';
    }
  }
}
