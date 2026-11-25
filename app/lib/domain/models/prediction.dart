/// Clase de la lesión según la tarea del modelo: melanoma frente a todas las
/// demás clases de HAM10000 (no benigno/maligno). Coincide con `ClaseLesion`
/// del backend (`melanoma` / `no_melanoma`).
enum LesionClass { melanoma, noMelanoma }

extension LesionClassLabel on LesionClass {
  String get label => this == LesionClass.melanoma ? 'Melanoma' : 'No melanoma';
}

/// Banda de la predicción preliminar, usada para sugerir exámenes adicionales
/// (RF-06.1). Equivale a la `banda` del backend: `sin_alerta`, `baja`,
/// `ambigua` y `alta`. "Sin alerta" no significa benigna: el modelo solo
/// evalúa melanoma y también deja sin alerta algunos melanomas.
enum PredictionConfidence { alta, ambigua, baja, sinAlerta }

/// Desempeño del modelo registrado en la evaluación única del test (EXP-04,
/// `resultados/exp04/20261114T005335Z_evaluacion-test`, población principal:
/// 294 lesiones con dos o más fotos, 57 melanomas). Son las cifras que se le
/// muestran al médico para leer una alerta; vienen de HAM10000, no de
/// pacientes peruanos.
abstract final class ReferencePerformance {
  /// Melanomas con alerta / melanomas (sensibilidad 91.2%).
  static const melanomasDetectados = 52;
  static const melanomas = 57;

  /// Alertas que no fueron melanoma / alertas (129 de 181, 71%).
  static const alertasSinMelanoma = 129;
  static const alertas = 181;

  /// "unas 7 de cada 10 alertas no fueron melanoma".
  static String get falseAlertsText =>
      'unas ${(alertasSinMelanoma * 10 / alertas).round()} de cada 10 alertas no fueron melanoma';

  /// "1 de cada 11 melanomas quedó por debajo de la línea de alerta".
  static String get missedText =>
      '1 de cada ${(melanomas / (melanomas - melanomasDetectados)).round()} melanomas '
      'quedó por debajo de la línea de alerta';

  /// "detectó 52 de 57 melanomas".
  static String get detectedText => 'detectó $melanomasDetectados de $melanomas melanomas';
}

/// Predicción preliminar devuelta por el módulo Inferencia (RF-03.3).
/// Nunca es un diagnóstico: siempre requiere validación médica.
class Prediction {
  const Prediction({
    required this.probabilidadMalignidad,
    required this.clasePredicha,
    required this.versionModelo,
    required this.umbralOperativo,
    required this.fechaInferencia,
    this.banda,
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

  /// El umbral operativo expresado como probabilidad calibrada (`linea_alerta`
  /// del backend), solo para mostrar la línea de alerta (EXP-04).
  final double umbralOperativo;
  final DateTime fechaInferencia;

  /// Banda calculada por el backend. Si falta (backend simulado), se calcula
  /// con los mismos cortes que `sugerencias.py`.
  final PredictionConfidence? banda;

  /// Por debajo de este riesgo se muestra "< 3%": la calibración da 0% a las
  /// salidas más bajas, y un 0% no está respaldado.
  static const _floor = 0.03;

  /// Por encima de este riesgo se muestra "> 90%": la calibración llega a
  /// 100% en su último tramo, estimado con muy pocas lesiones.
  static const _ceiling = 0.90;

  int get percent => (probabilidadMalignidad * 100).round();

  int get alertPercent => (umbralOperativo * 100).round();

  bool get isAlert => clasePredicha == LesionClass.melanoma;

  // Textos para el médico, sin términos de aprendizaje automático: la
  // probabilidad calibrada se presenta como "riesgo estimado" y el umbral
  // operativo como "línea de alerta".
  //
  // Sin alerta no se muestra el porcentaje: por el escalón de la calibración,
  // un caso sin alerta puede tener el mismo 7% que uno con alerta, y un
  // número junto a "Sin alerta" se lee como tranquilizador.

  /// Resultado preliminar en una frase corta.
  String get headline => isAlert ? 'Posible melanoma' : 'Sin alerta de melanoma';

  /// El riesgo estimado con piso y techo ("< 3%", "> 90%").
  String get riskText {
    final p = probabilidadMalignidad;
    if (p < _floor) return '< ${(_floor * 100).round()}%';
    if (p > _ceiling) return '> ${(_ceiling * 100).round()}%';
    return '$percent%';
  }

  /// El riesgo como frecuencia natural, atada al conjunto con el que se
  /// calibró (HAM10000, donde 1 de cada 5 lesiones con varias fotos era
  /// melanoma). Nula sin alerta.
  String? get frequencyText {
    if (!isAlert) return null;
    final p = probabilidadMalignidad;
    final n = p < _floor
        ? 'menos de ${(_floor * 100).round()}'
        : p > _ceiling
            ? 'más de ${(_ceiling * 100).round()}'
            : 'unas $percent';
    return 'En las lesiones con las que se desarrolló el sistema, $n de cada 100 '
        'con este resultado fueron melanoma.';
  }

  /// Qué esperar de este resultado, con las cifras de la evaluación.
  String get contextText => isAlert
      ? 'El sistema avisa desde un $alertPercent% de riesgo para no pasar por alto '
          'melanomas; en sus pruebas, ${ReferencePerformance.falseAlertsText}.'
      : 'No descarta un melanoma: en las pruebas del sistema, '
          '${ReferencePerformance.missedText}.';

  /// Lo que el sistema no evalúa (el paper, V-C: un "no melanoma" en un
  /// carcinoma basocelular puede tranquilizar en falso).
  static const scopeText =
      'Solo evalúa melanoma: no descarta otros cánceres de piel, como el carcinoma basocelular.';

  /// Resumen de una línea para listas, historial y validación.
  String get shortSummary => isAlert ? '$headline · riesgo $riskText' : headline;

  PredictionConfidence get confidence {
    final b = banda;
    if (b != null) return b;
    final p = probabilidadMalignidad;
    if (clasePredicha == LesionClass.noMelanoma) return PredictionConfidence.sinAlerta;
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
      case PredictionConfidence.sinAlerta:
        return null;
    }
  }

  /// Nivel de riesgo de una alerta. Nulo sin alerta: llamar "bajo" o "muy
  /// bajo" a un caso sin alerta no está respaldado.
  String? get riskLevel {
    switch (confidence) {
      case PredictionConfidence.alta:
        return 'alto';
      case PredictionConfidence.ambigua:
        return 'intermedio';
      case PredictionConfidence.baja:
        return 'bajo';
      case PredictionConfidence.sinAlerta:
        return null;
    }
  }

  String get riskLabel {
    final level = riskLevel;
    return level == null ? 'Por debajo de la línea de alerta' : 'Riesgo $level';
  }
}
