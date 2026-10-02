"""Estrategias de desbalance (EXP-03): sin balanceo, pesos de clase, sobremuestreo y focal loss.

`training.imbalance` elige la estrategia y `setup` traduce la configuración a lo que necesita el
entrenamiento: la pérdida, los pesos de clase y la fracción de melanomas por lote. Todas tocan solo
el entrenamiento; la validación y el test no se remuestrean ni se reponderan (HU15).
"""

from __future__ import annotations

from typing import Any

import keras
import numpy as np

STRATEGIES = ("none", "class_weight", "oversampling", "focal_loss")


def class_weights(labels: np.ndarray) -> dict[int, float]:
    """Pesos "balanced": n / (2 · n_clase), así cada clase pesa lo mismo en la pérdida total."""
    labels = np.asarray(labels).astype(int)
    counts = np.bincount(labels, minlength=2)
    if counts.min() == 0:
        raise ValueError("Se necesitan ejemplos de las dos clases para calcular los pesos")
    return {c: float(len(labels) / (2 * counts[c])) for c in (0, 1)}


def setup(training_cfg: dict[str, Any], train_labels: np.ndarray) -> dict[str, Any]:
    """{"loss", "class_weight", "positive_fraction"} para la estrategia de `training.imbalance`."""
    strategy = training_cfg.get("imbalance", "none")
    if strategy not in STRATEGIES:
        raise ValueError(f"Estrategia de desbalance desconocida {strategy!r}; opciones: {STRATEGIES}")
    out: dict[str, Any] = {"loss": "binary_crossentropy", "class_weight": None,
                           "positive_fraction": None}
    if strategy == "class_weight":
        out["class_weight"] = class_weights(train_labels)
    elif strategy == "oversampling":
        out["positive_fraction"] = float(training_cfg["oversampling_positive_fraction"])
    elif strategy == "focal_loss":
        # Lin et al. (2017): baja el peso de los ejemplos que el modelo ya clasifica bien.
        out["loss"] = keras.losses.BinaryFocalCrossentropy(gamma=float(training_cfg["focal_gamma"]))
    return out
