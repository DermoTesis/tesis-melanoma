"""Sugerencia editable de exámenes adicionales cuando la predicción es incierta (RF-06.1, HU29).

Usa las mismas bandas y textos que la app (`Prediction.defaultSuggestion`), para que la fuente
de verdad pase a ser el backend sin que el médico vea un cambio. Las bandas se calculan con la
probabilidad calibrada y solo en los casos con alerta:

- sin alerta: sin sugerencia;
- baja (< 0.30) y ambigua (0.30–0.70): con sugerencia;
- alta (>= 0.70): sin sugerencia (la alerta ya es clara).

Los cortes 0.30 y 0.70 no salen de un experimento (pendiente A7 de `app/PENDIENTES.md`): sobre
las predicciones de validación, separan bandas con 13%, 44% y 79% de melanomas.
"""

from __future__ import annotations

from .modelos import ClaseLesion, Prediccion

CORTE_AMBIGUA = 0.30
CORTE_ALTA = 0.70

SUGERENCIA_AMBIGUA = (
    "Considerar dermatoscopia digital de seguimiento o biopsia para descartar un falso "
    "positivo antes de concluir."
)
SUGERENCIA_BAJA = (
    "Riesgo bajo, pero por encima de la línea de alerta. Considerar control dermatoscópico "
    "en 3 meses o biopsia según hallazgos."
)


def banda(prediccion: Prediccion) -> str:
    if prediccion.clase_predicha == ClaseLesion.NO_MELANOMA:
        return "sin_alerta"
    if prediccion.probabilidad_malignidad >= CORTE_ALTA:
        return "alta"
    if prediccion.probabilidad_malignidad >= CORTE_AMBIGUA:
        return "ambigua"
    return "baja"


def sugerencia_por_defecto(prediccion: Prediccion) -> str | None:
    return {"ambigua": SUGERENCIA_AMBIGUA, "baja": SUGERENCIA_BAJA}.get(banda(prediccion))
