"""Estrategias de desbalance: sin balanceo, pesos de clase, sobremuestreo y dos pérdidas.

`training.imbalance` elige la estrategia y `setup` traduce la configuración a lo que necesita el
entrenamiento: la pérdida, los pesos de clase y la fracción de melanomas por lote. Todas tocan solo
el entrenamiento; la validación y el test no se remuestrean ni se reponderan (HU15).

- `focal_loss` (EXP-03, EXP-08): Lin et al. (2017). `training.focal_gamma` es γ; con
  `training.focal_alpha` (p. ej. 0.25, el de Lin et al.) se aplica además el balanceo α, que pesa α
  a los melanomas y 1 − α al resto. Sin `focal_alpha` (EXP-03) no hay balanceo α.
- `asymmetric_loss` (EXP-08): Ridnik et al. (2021), ver `melanoma.losses`. Parámetros
  `training.asl_gamma_pos`, `asl_gamma_neg` y `asl_clip` (por defecto 0, 4 y 0.05).

El modelo de dos fotos y el modelo final solo admiten las estrategias que cambian la pérdida
(`loss_only`): los pesos de clase y el sobremuestreo no están implementados ahí.
"""

from __future__ import annotations

from typing import Any

import keras
import numpy as np

from melanoma.losses import AsymmetricLoss

STRATEGIES = ("none", "class_weight", "oversampling", "focal_loss", "asymmetric_loss")
LOSS_STRATEGIES = ("none", "focal_loss", "asymmetric_loss")


def class_weights(labels: np.ndarray) -> dict[int, float]:
    """Pesos "balanced": n / (2 · n_clase), así cada clase pesa lo mismo en la pérdida total."""
    labels = np.asarray(labels).astype(int)
    counts = np.bincount(labels, minlength=2)
    if counts.min() == 0:
        raise ValueError("Se necesitan ejemplos de las dos clases para calcular los pesos")
    return {c: float(len(labels) / (2 * counts[c])) for c in (0, 1)}


def make_loss(training_cfg: dict[str, Any]) -> str | keras.losses.Loss:
    """La pérdida de la estrategia (entropía cruzada binaria si la estrategia no la cambia)."""
    strategy = training_cfg.get("imbalance", "none")
    if strategy == "focal_loss":
        # Lin et al. (2017): baja el peso de los ejemplos que el modelo ya clasifica bien.
        alpha = training_cfg.get("focal_alpha")
        if alpha is None:
            return keras.losses.BinaryFocalCrossentropy(gamma=float(training_cfg["focal_gamma"]))
        return keras.losses.BinaryFocalCrossentropy(gamma=float(training_cfg["focal_gamma"]),
                                                    apply_class_balancing=True, alpha=float(alpha))
    if strategy == "asymmetric_loss":
        return AsymmetricLoss(gamma_pos=float(training_cfg.get("asl_gamma_pos", 0.0)),
                              gamma_neg=float(training_cfg.get("asl_gamma_neg", 4.0)),
                              clip=float(training_cfg.get("asl_clip", 0.05)))
    return "binary_crossentropy"


def setup(training_cfg: dict[str, Any], train_labels: np.ndarray) -> dict[str, Any]:
    """{"loss", "class_weight", "positive_fraction"} para la estrategia de `training.imbalance`."""
    strategy = training_cfg.get("imbalance", "none")
    if strategy not in STRATEGIES:
        raise ValueError(f"Estrategia de desbalance desconocida {strategy!r}; opciones: {STRATEGIES}")
    out: dict[str, Any] = {"loss": make_loss(training_cfg), "class_weight": None,
                           "positive_fraction": None}
    if strategy == "class_weight":
        out["class_weight"] = class_weights(train_labels)
    elif strategy == "oversampling":
        out["positive_fraction"] = float(training_cfg["oversampling_positive_fraction"])
    return out


def loss_only(training_cfg: dict[str, Any]) -> str | keras.losses.Loss:
    """La pérdida, para los entrenamientos que no admiten pesos de clase ni sobremuestreo."""
    strategy = training_cfg.get("imbalance", "none")
    if strategy not in LOSS_STRATEGIES:
        raise ValueError(f"La estrategia {strategy!r} no está implementada para este modelo; "
                         f"solo {LOSS_STRATEGIES}")
    return make_loss(training_cfg)
