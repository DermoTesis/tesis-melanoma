"""Pérdida asimétrica (ASL) de Ridnik et al., ICCV 2021, para la salida sigmoide (EXP-08).

Con p la probabilidad de melanoma, y = 1 melanoma, y m el margen:

- positivos: L+ = (1 − p)^γ+ · log(p);
- negativos: L− = p_m^γ− · log(1 − p_m), con p_m = max(p − m, 0).

El margen anula la pérdida (y el gradiente) de los negativos fáciles, los que el modelo ya da por
benignos con p < m, y γ− > γ+ baja el peso del resto de los negativos fáciles. Así el
entrenamiento se concentra en los benignos que se parecen al melanoma, que son los que dan las
falsas alarmas con sensibilidad 90%.

Sigue la implementación oficial (Alibaba-MIIL/ASL, `AsymmetricLoss` en
`src/loss_functions/losses.py`; el entrenamiento oficial usa γ− = 4, γ+ = 0 y m = 0.05):
- el margen se aplica como 1 − p_m = min(1 − p + m, 1);
- el peso de enfoque (1 − p_t)^γ se calcula sin gradiente (`disable_torch_grad_focal_loss=True`).
Ellos suman la pérdida; aquí se promedia, como las demás pérdidas de Keras (Adam casi no depende
de la escala).
"""

from __future__ import annotations

from typing import Any

import keras
from keras import ops


@keras.saving.register_keras_serializable(package="melanoma")
class AsymmetricLoss(keras.losses.Loss):
    """ASL para clasificación binaria con salida sigmoide (`y_pred` es una probabilidad)."""

    def __init__(self, gamma_pos: float = 0.0, gamma_neg: float = 4.0, clip: float = 0.05,
                 eps: float = 1e-8, stop_gradient_weights: bool = True,
                 name: str = "asymmetric_loss", reduction: str = "sum_over_batch_size",
                 dtype: Any = None) -> None:
        super().__init__(name=name, reduction=reduction, dtype=dtype)
        if gamma_pos < 0 or gamma_neg < 0 or not 0 <= clip < 1:
            raise ValueError("Se espera gamma_pos, gamma_neg >= 0 y 0 <= clip < 1")
        self.gamma_pos = float(gamma_pos)
        self.gamma_neg = float(gamma_neg)
        self.clip = float(clip)
        self.eps = float(eps)
        self.stop_gradient_weights = bool(stop_gradient_weights)

    def call(self, y_true, y_pred):
        y_pred = ops.convert_to_tensor(y_pred)
        p = ops.cast(y_pred, "float32")
        y = ops.cast(ops.reshape(y_true, ops.shape(p)), "float32")
        q = 1.0 - p                                    # probabilidad de "no melanoma"
        if self.clip > 0:
            q = ops.minimum(q + self.clip, 1.0)        # 1 − p_m
        loss = y * ops.log(ops.maximum(p, self.eps)) + (1.0 - y) * ops.log(ops.maximum(q, self.eps))
        if self.gamma_pos > 0 or self.gamma_neg > 0:
            p_t = y * p + (1.0 - y) * q
            gamma = y * self.gamma_pos + (1.0 - y) * self.gamma_neg
            weight = ops.power(1.0 - p_t, gamma)
            if self.stop_gradient_weights:
                weight = ops.stop_gradient(weight)
            loss = loss * weight
        return -loss

    def get_config(self) -> dict[str, Any]:
        return {**super().get_config(), "gamma_pos": self.gamma_pos, "gamma_neg": self.gamma_neg,
                "clip": self.clip, "eps": self.eps,
                "stop_gradient_weights": self.stop_gradient_weights}
