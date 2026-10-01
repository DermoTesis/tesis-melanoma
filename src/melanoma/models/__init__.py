"""Modelos: MobileNetV3-Large con pesos de ImageNet y una cabeza densa que da la probabilidad de
melanoma (EXP-02), de extremo a extremo y sin Random Forest (memoria v5, backlog v4).

El modelo recibe la imagen en rango 0-255: MobileNetV3 trae su preprocesamiento, así que el
`.tflite` recibe los píxeles tal cual. EXP-06 agrega la variante de dos fotos.
"""

from melanoma.models.single_view import backbone, build_single_view

__all__ = ["backbone", "build_single_view"]
