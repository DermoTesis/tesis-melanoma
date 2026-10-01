"""Clasificador de una foto: MobileNetV3-Large → pooling promedio → dropout → densa sigmoide."""

from __future__ import annotations

from typing import Any

import keras

BACKBONES = {"mobilenet_v3_large": keras.applications.MobileNetV3Large}


def build_single_view(model_cfg: dict[str, Any], image_size: int,
                      weights: str | None = "from_config") -> keras.Model:
    """Arma el modelo con el backbone como una sola capa (un `keras.Model` anidado).

    El backbone se llama con `training=False`, así sus BatchNorm quedan en modo inferencia también
    durante el fine-tuning. `weights` permite forzar `None` en las pruebas (sin descargar).
    """
    if model_cfg["backbone"] not in BACKBONES:
        raise ValueError(f"Backbone desconocido {model_cfg['backbone']!r}; opciones: {list(BACKBONES)}")
    if weights == "from_config":
        weights = model_cfg.get("weights")
    base = BACKBONES[model_cfg["backbone"]](
        input_shape=(image_size, image_size, 3), include_top=False, weights=weights,
        pooling="avg", include_preprocessing=True)

    inputs = keras.Input((image_size, image_size, 3), name="image")
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
