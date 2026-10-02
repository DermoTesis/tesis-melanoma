"""Métricas: Accuracy, Precision, Recall, F1, AUC-ROC, PR-AUC, especificidad y matriz de confusión,
con IC 95% por bootstrap. Las usan EXP-02 en adelante.

El bootstrap remuestrea lesiones, no imágenes: las imágenes de una misma lesión están
correlacionadas (en HAM10000 los melanomas tienen 1.8 imágenes por lesión en promedio), así que
remuestrear imágenes daría intervalos demasiado estrechos.

Se predice melanoma cuando la probabilidad es >= umbral. Cada métrica de umbral lleva un sufijo:
- `_t50`: umbral 0.5;
- `_s90`: el umbral más alto con sensibilidad >= 90% en los mismos datos. Es optimista (el umbral se
  elige donde se mide), así que solo sirve para comparar candidatos; el umbral operativo se fija
  en EXP-04 con validación y se mide una sola vez en el test.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

COUNTS = ("tp", "fp", "tn", "fn")


def at_threshold(y: np.ndarray, p: np.ndarray, threshold: float) -> dict[str, float]:
    """Métricas de la matriz de confusión con predicción positiva si p >= threshold."""
    y = np.asarray(y).astype(bool)
    pred = np.asarray(p) >= threshold
    tp = int(np.sum(pred & y))
    fp = int(np.sum(pred & ~y))
    tn = int(np.sum(~pred & ~y))
    fn = int(np.sum(~pred & y))
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    return {
        "accuracy": _ratio(tp + tn, len(y)),
        "precision": precision,
        "recall": recall,
        "specificity": _ratio(tn, tn + fp),
        "f1": _ratio(2 * precision * recall, precision + recall),
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
    }


def threshold_for_recall(y: np.ndarray, p: np.ndarray, target: float) -> float:
    """El umbral más alto con recall >= target: la k-ésima probabilidad más alta entre los
    positivos, con k = ceil(target · positivos)."""
    pos = np.sort(np.asarray(p)[np.asarray(y).astype(bool)])[::-1]
    if len(pos) == 0:
        return math.nan
    k = max(1, math.ceil(target * len(pos) - 1e-9))
    return float(pos[k - 1])


def point_metrics(y: np.ndarray, p: np.ndarray, target_recall: float = 0.90) -> dict[str, float]:
    """AUC-ROC, PR-AUC y las métricas en el umbral 0.5 y en el de sensibilidad objetivo."""
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    both = 0 < y.sum() < len(y)
    out: dict[str, float] = {
        "auc_roc": float(roc_auc_score(y, p)) if both else math.nan,
        "pr_auc": float(average_precision_score(y, p)) if both else math.nan,
    }
    out.update({f"{k}_t50": v for k, v in at_threshold(y, p, 0.5).items()})
    suffix = f"s{round(target_recall * 100)}"
    threshold = threshold_for_recall(y, p, target_recall)
    out[f"threshold_{suffix}"] = threshold
    out.update({f"{k}_{suffix}": v for k, v in at_threshold(y, p, threshold).items()})
    return out


def bootstrap_indices(groups: Sequence, n_resamples: int, seed: int):
    """Genera índices de imágenes remuestreando grupos (lesiones) con reemplazo: cada lesión
    elegida aporta todas sus imágenes."""
    codes, _ = pd.factorize(np.asarray(groups))
    order = np.argsort(codes, kind="stable")
    counts = np.bincount(codes)
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    rng = np.random.default_rng(seed)
    for _ in range(n_resamples):
        chosen = rng.integers(0, len(counts), len(counts))
        lens = counts[chosen]
        offsets = np.repeat(starts[chosen] - np.concatenate([[0], np.cumsum(lens)[:-1]]), lens)
        yield order[offsets + np.arange(lens.sum())]


def evaluate(y: np.ndarray, p: np.ndarray, groups: Sequence, target_recall: float = 0.90,
             n_resamples: int = 2000, confidence: float = 0.95, seed: int = 42) -> dict[str, Any]:
    """Métricas puntuales más IC por bootstrap de lesiones (`<métrica>_ci_low`/`_ci_high`).

    En cada remuestreo se recalculan todas las métricas, incluido el umbral de sensibilidad
    objetivo. Los remuestreos sin positivos o sin negativos se descartan para el AUC.
    """
    y = np.asarray(y).astype(int)
    p = np.asarray(p, dtype=float)
    point = point_metrics(y, p, target_recall)
    keys = [k for k in point if k.split("_")[0] not in COUNTS]
    samples = []
    for idx in bootstrap_indices(groups, n_resamples, seed):
        resampled = point_metrics(y[idx], p[idx], target_recall)
        samples.append([resampled[k] for k in keys])
    samples = np.array(samples)
    alpha = (1 - confidence) / 2
    low = np.nanquantile(samples, alpha, axis=0)
    high = np.nanquantile(samples, 1 - alpha, axis=0)
    out: dict[str, Any] = dict(point)
    for key, lo, hi in zip(keys, low, high):
        out[f"{key}_ci_low"] = float(lo)
        out[f"{key}_ci_high"] = float(hi)
    out["n_images"] = int(len(y))
    out["n_lesions"] = int(pd.Series(groups).nunique())
    out["n_positive_images"] = int(y.sum())
    return out


def compare_paired(y: np.ndarray, p_reference: np.ndarray, p_candidate: np.ndarray,
                   groups: Sequence, target_recall: float = 0.90, n_resamples: int = 2000,
                   confidence: float = 0.95, seed: int = 42,
                   keys: Sequence[str] = ("auc_roc", "pr_auc", "specificity_s90")) -> dict[str, float]:
    """Diferencia candidato − referencia sobre las mismas imágenes, con IC por bootstrap pareado.

    En cada remuestreo de lesiones se evalúan los dos modelos sobre la misma muestra, así el IC
    refleja solo la diferencia entre ellos y no la dificultad de la muestra. Si el IC incluye el 0,
    la diferencia no está demostrada. `specificity_s90` usa el sufijo de `target_recall`.
    """
    y = np.asarray(y).astype(int)
    a, b = np.asarray(p_reference, dtype=float), np.asarray(p_candidate, dtype=float)
    suffix = f"s{round(target_recall * 100)}"
    keys = [k.replace("s90", suffix) for k in keys]

    def delta(idx: np.ndarray) -> list[float]:
        ma = point_metrics(y[idx], a[idx], target_recall)
        mb = point_metrics(y[idx], b[idx], target_recall)
        return [mb[k] - ma[k] for k in keys]

    point = delta(np.arange(len(y)))
    samples = np.array([delta(idx) for idx in bootstrap_indices(groups, n_resamples, seed)])
    alpha = (1 - confidence) / 2
    out: dict[str, float] = {}
    for i, key in enumerate(keys):
        out[f"delta_{key}"] = float(point[i])
        out[f"delta_{key}_ci_low"] = float(np.nanquantile(samples[:, i], alpha))
        out[f"delta_{key}_ci_high"] = float(np.nanquantile(samples[:, i], 1 - alpha))
    return out


def cv_summary(fold_rows: list[dict[str, Any]], keys: Sequence[str] | None = None) -> dict[str, dict]:
    """Media y desviación estándar (muestral) de cada métrica entre folds."""
    df = pd.DataFrame(fold_rows)
    keys = keys or [k for k in df.columns if pd.api.types.is_float_dtype(df[k])]
    return {k: {"mean": float(df[k].mean()), "std": float(df[k].std(ddof=1)) if len(df) > 1 else 0.0}
            for k in keys}


def _ratio(num: float, den: float) -> float:
    return float(num / den) if den else 0.0
