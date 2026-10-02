"""Figuras para la memoria: matriz de confusión y desglose por diagnóstico de HAM10000.

Se generan aparte, en CPU, a partir de las predicciones guardadas de cada corrida
(`scripts/matriz_confusion.py`), así el entrenamiento en la GPU no necesita matplotlib.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd

from melanoma.metrics import at_threshold

# Diagnósticos de HAM10000, en el orden en que se muestran.
DIAGNOSES = {
    "mel": "Melanoma",
    "nv": "Nevus melanocítico",
    "bkl": "Queratosis benigna",
    "bcc": "Carcinoma basocelular",
    "akiec": "Queratosis actínica",
    "df": "Dermatofibroma",
    "vasc": "Lesión vascular",
}
CLASSES = ["Melanoma", "No melanoma"]


def confusion_table(y: Sequence, p: Sequence, threshold: float) -> np.ndarray:
    """[[VP, FN], [FP, VN]]: filas = real (melanoma, no melanoma), columnas = predicción."""
    m = at_threshold(np.asarray(y), np.asarray(p), threshold)
    return np.array([[m["tp"], m["fn"]], [m["fp"], m["tn"]]])


def by_diagnosis(dx: Sequence, p: Sequence, threshold: float) -> pd.DataFrame:
    """Por diagnóstico real: imágenes, cuántas se predicen como melanoma y qué fracción."""
    df = pd.DataFrame({"dx": np.asarray(dx), "melanoma": np.asarray(p) >= threshold})
    out = df.groupby("dx").melanoma.agg(images="size", predicted_melanoma="sum")
    out["fraction"] = out.predicted_melanoma / out.images
    order = [d for d in DIAGNOSES if d in out.index] + sorted(set(out.index) - set(DIAGNOSES))
    return out.loc[order]


def plot_matrices(panels: list[tuple[str, np.ndarray]], row_labels: Sequence[str],
                  path: str | Path, title: str | None = None) -> Path:
    """Una matriz de conteos por panel, con columnas Melanoma / No melanoma (predicción).

    El color y el porcentaje son por fila: en la fila de melanoma, la celda de la izquierda es la
    sensibilidad; en la de no melanoma, la de la derecha es la especificidad.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n_rows = len(row_labels)
    fig, axes = plt.subplots(1, len(panels), figsize=(4.6 * len(panels) + 1.2, 1.0 + 0.75 * n_rows),
                             squeeze=False, constrained_layout=True)
    for ax, (panel_title, counts) in zip(axes[0], panels):
        counts = np.asarray(counts)
        share = counts / np.maximum(counts.sum(axis=1, keepdims=True), 1)
        ax.imshow(share, cmap="Blues", vmin=0, vmax=1, aspect="auto")
        for i in range(n_rows):
            for j in range(2):
                color = "white" if share[i, j] > 0.6 else "black"
                ax.text(j, i, f"{counts[i, j]:,}\n({share[i, j]:.1%})", ha="center", va="center",
                        color=color, fontsize=10)
        ax.set_xticks(range(2), CLASSES)
        ax.set_yticks(range(n_rows), row_labels)
        ax.set_xlabel("Predicción del modelo")
        ax.set_title(panel_title, fontsize=11)
        ax.tick_params(length=0)
    axes[0][0].set_ylabel("Diagnóstico real")
    if title:
        fig.suptitle(title, fontsize=12)
    path = Path(path)
    fig.savefig(path, dpi=200)
    plt.close(fig)
    return path
