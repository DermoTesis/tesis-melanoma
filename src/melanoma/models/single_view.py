"""Clasificador de una foto: backbone → pooling promedio → dropout → densa sigmoide.

El backbone del modelo es MobileNetV3-Large. EfficientNetV2-B0 y EfficientNetV2-S solo se usan
para medir cuánto se pierde con él (EXP-11). Los tres traen su propio preprocesamiento y reciben
píxeles 0-255.
"""

from __future__ import annotations

from typing import Any

import keras

BACKBONES = {"mobilenet_v3_large": keras.applications.MobileNetV3Large,
             "efficientnet_v2_b0": keras.applications.EfficientNetV2B0,
             "efficientnet_v2_s": keras.applications.EfficientNetV2S}


def build_single_view(model_cfg: dict[str, Any], image_size: int,
                      weights: str | None = "from_config") -> keras.Model:
    """Arma el modelo con el backbone como una sola capa (un `keras.Model` anidado).

    `weights` permite forzar `None` en las pruebas (sin descargar).
    """
    if model_cfg["backbone"] not in BACKBONES:
        raise ValueError(f"Backbone desconocido {model_cfg['backbone']!r}; opciones: {list(BACKBONES)}")
    if weights == "from_config":
        weights = model_cfg.get("weights")
    base = BACKBONES[model_cfg["backbone"]](
        input_shape=(image_size, image_size, 3), include_top=False, weights=weights,
        pooling="avg", include_preprocessing=True)

    inputs = keras.Input((image_size, image_size, 3), name="image")
    # Keras 3 ignora este training=False cuando el modelo entrena: las BatchNorm se mantienen en
    # modo inferencia congelándolas (`unfreeze_backbone`).
    features = base(inputs, training=False)
    x = keras.layers.Dropout(model_cfg.get("dropout", 0.0), name="dropout")(features)
    # float32 a la salida aunque el resto vaya en precisión mixta.
    outputs = keras.layers.Dense(1, activation="sigmoid", dtype="float32", name="melanoma")(x)
    return keras.Model(inputs, outputs, name=f"{model_cfg['backbone']}_single_view")


def backbone(model: keras.Model) -> keras.Model:
    """El backbone es la única capa del modelo que es a su vez un modelo."""
    nested = [layer for layer in model.layers if isinstance(layer, keras.Model)]
    if len(nested) != 1:
        raise ValueError(f"Se esperaba un backbone anidado en {model.name}, hay {len(nested)}")
    return nested[0]


def unfreeze_backbone(model: keras.Model) -> None:
    """Descongela el backbone para el fine-tuning, salvo sus capas BatchNormalization.

    Congeladas, siguen en modo inferencia con las estadísticas de ImageNet, como recomienda la guía
    de transfer learning de Keras. Entrenables pasarían a normalizar con las de cada lote de 32.
    """
    base = backbone(model)
    base.trainable = True
    for layer in base.layers:
        if isinstance(layer, keras.layers.BatchNormalization):
            layer.trainable = False
