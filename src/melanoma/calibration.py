"""Calibración y umbral (EXP-04).

- Calibración: Platt (logística sobre el logit) o isotónica, elegida por ECE con validación
  cruzada sobre las predicciones fuera de fold. Sirve para mostrarle al médico una probabilidad
  interpretable; no cambia el orden de los casos.
- Umbral con margen: el modelo dice "melanoma" si su salida (sin calibrar) es >= umbral. El umbral
  se elige para que, con `confidence` de confianza, la sensibilidad sea al menos `target`: en cada
  remuestreo de lesiones se calcula el umbral que da justo `target`, y se toma el cuantil
  1 − confidence de esos umbrales. Así, si el test se parece a la validación, la sensibilidad
  queda sobre `target` en ese porcentaje de los casos.

La decisión usa la salida sin calibrar para que una isotónica (que tiene escalones) no cambie qué
casos quedan sobre el umbral; la probabilidad calibrada del umbral se guarda para mostrarla.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from melanoma.metrics import bootstrap_indices, threshold_for_recall

EPS = 1e-6


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def fit(method: str, y: np.ndarray, p: np.ndarray) -> dict[str, Any]:
    """Parámetros de la calibración, serializables a JSON."""
    y = np.asarray(y).astype(int)
    if method == "platt":
        lr = LogisticRegression(C=1e6, max_iter=1000).fit(_logit(p)[:, None], y)
        return {"method": "platt", "a": float(lr.coef_[0, 0]), "b": float(lr.intercept_[0])}
    if method == "isotonic":
        iso = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip").fit(p, y)
        return {"method": "isotonic", "x": iso.X_thresholds_.tolist(), "y": iso.y_thresholds_.tolist()}
    raise ValueError(f"Calibración desconocida {method!r}: platt o isotonic")


def apply(params: dict[str, Any], p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    if params["method"] == "platt":
        return 1 / (1 + np.exp(-(params["a"] * _logit(p) + params["b"])))
    return np.interp(p, params["x"], params["y"])


def ece(y: np.ndarray, p: np.ndarray, bins: int = 15) -> float:
    """Error de calibración esperado con bins de igual ancho."""
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    edges = np.linspace(0, 1, bins + 1)
    which = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    total = 0.0
    for b in range(bins):
        mask = which == b
        if mask.any():
            total += mask.mean() * abs(y[mask].mean() - p[mask].mean())
    return float(total)


def choose(y: np.ndarray, p: np.ndarray, folds: np.ndarray, methods: Sequence[str],
           bins: int = 15) -> dict[str, Any]:
    """Elige la calibración por ECE fuera de fold y la ajusta con todos los datos.

    Para cada fold, la calibración se ajusta con los otros y se aplica a ese, así el ECE no se mide
    con los mismos datos con que se ajustó.
    """
    y, p, folds = np.asarray(y), np.asarray(p, dtype=float), np.asarray(folds)
    scores = {"none": {"ece": ece(y, p, bins), "brier": float(np.mean((p - y) ** 2))}}
    for method in methods:
        out = np.empty_like(p)
        for k in np.unique(folds):
            test = folds == k
            out[test] = apply(fit(method, y[~test], p[~test]), p[test])
        scores[method] = {"ece": ece(y, out, bins), "brier": float(np.mean((out - y) ** 2))}
    best = min(methods, key=lambda m: scores[m]["ece"])
    return {"chosen": best, "scores": scores, "params": fit(best, y, p)}


def threshold_with_margin(y: np.ndarray, p: np.ndarray, groups: Sequence, target: float,
                          confidence: float, n_resamples: int, seed: int) -> dict[str, float]:
    """Umbral con el que la sensibilidad es >= `target` con `confidence` de confianza."""
    y, p = np.asarray(y).astype(int), np.asarray(p, dtype=float)
    samples = [threshold_for_recall(y[i], p[i], target)
               for i in bootstrap_indices(groups, n_resamples, seed)]
    samples = np.array([t for t in samples if np.isfinite(t)])
    return {"threshold": float(np.quantile(samples, 1 - confidence)),
            "threshold_no_margin": threshold_for_recall(y, p, target),
            "target_recall": target, "confidence": confidence, "n_resamples": int(len(samples))}
