"""Modelos (EXP-02): backbones MobileNetV2 y MobileNetV3-Large con pesos de ImageNet, cabeza densa
y Random Forest sobre las features del backbone ya ajustado.

Todos los modelos reciben la imagen en rango 0-255: MobileNetV3 trae su preprocesamiento y a
MobileNetV2 se le agrega como capa, así el `.tflite` recibe los píxeles tal cual.
"""
