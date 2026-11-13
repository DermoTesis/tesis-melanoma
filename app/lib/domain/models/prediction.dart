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

  /// Probabilidad calibrada (regresión isotónica) de malignidad, 0..1. Es el
  /// número que ve el médico; no decide la clase.
  final double probabilidadMalignidad;

  /// Clase decidida por el backend con la salida sin calibrar del modelo
  /// (EXP-04). La app nunca la recalcula a partir de la probabilidad
  /// calibrada: por los escalones de la calibración, ambos cortes no
  /// coinciden.
  final LesionClass clasePredicha;
  final String versionModelo;

  /// El umbral operativo expresado como probabilidad calibrada, solo para
  /// mostrar la línea de alerta (EXP-04).
  final double umbralOperativo;
  final DateTime fechaInferencia;

  int get percent => (probabilidadMalignidad * 100).round();

  int get alertPercent => (umbralOperativo * 100).round();

  bool get isAlert => clasePredicha == LesionClass.maligno;

  // Textos para el médico, sin términos de aprendizaje automático: la
  // probabilidad calibrada se presenta como "riesgo estimado" y el umbral
  // operativo como "línea de alerta".

  /// Resultado preliminar en una frase corta.
  String get headline => isAlert ? 'Posible melanoma' : 'Sin alerta de melanoma';

  /// La probabilidad expresada como frecuencia natural.
  String get frequencyText {
    final n = percent < 1 ? 'Menos de 1' : 'Unas $percent';
    return '$n de cada 100 lesiones con este resultado son melanoma.';
  }

  /// Resumen de una línea para listas, historial y validación.
  String get shortSummary => '$headline · riesgo $percent%';

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
        return 'Riesgo bajo, pero por encima de la línea de alerta. Considerar '
            'control dermatoscópico en 3 meses o biopsia según hallazgos.';
      case PredictionConfidence.alta:
      case PredictionConfidence.benigna:
        return null;
    }
  }

  String get riskLevel {
    switch (confidence) {
      case PredictionConfidence.alta:
        return 'alto';
      case PredictionConfidence.ambigua:
        return 'intermedio';
      case PredictionConfidence.baja:
        return 'bajo';
      case PredictionConfidence.benigna:
        return 'muy bajo';
    }
  }

  String get riskLabel => 'Riesgo $riskLevel';
}
