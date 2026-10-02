"""Matrices de confusión de una corrida, a partir de sus predicciones guardadas.

    python scripts/matriz_confusion.py resultados/exp02/<corrida> [--umbral 0.3]

Genera en la carpeta de la corrida:
- matriz_confusion.png: real vs. predicción con el umbral 0.5 y con el de sensibilidad objetivo
  (90%), que se elige en los mismos datos: es optimista y solo sirve para comparar candidatos;
- matriz_por_diagnostico.png y .csv: cuántas imágenes de cada diagnóstico de HAM10000 se predicen
  como melanoma con esos umbrales.

`--umbral` agrega otros umbrales, p. ej. el operativo de EXP-04.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from melanoma.figures import DIAGNOSES, by_diagnosis, confusion_table, plot_matrices


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("corrida", type=Path, help="carpeta de la corrida en resultados/")
    parser.add_argument("--predicciones", default="predicciones_val.csv")
    parser.add_argument("--umbral", type=float, action="append", default=[])
    args = parser.parse_args()

    run = args.corrida
    pred = pd.read_csv(run / args.predicciones)
    target = yaml.safe_load((run / "config.yaml").read_text())["metrics"]["target_recall"]
    rows = json.loads((run / "metricas.json").read_text())["rows"]
    pooled = next(r for r in rows if r["fold"] == "oof")
    thresholds = [("Umbral 0.5", 0.5)]
    t_target = pooled[f"threshold_s{round(target * 100)}"]
    thresholds.append((f"Sensibilidad {target:.0%} (umbral {t_target:.3f})", t_target))
    thresholds += [(f"Umbral {t:g}", t) for t in args.umbral]

    source = f"{run.parent.name.upper().replace('EXP', 'EXP-')} · {len(pred):,} imágenes"
    panels = [(name, confusion_table(pred.label, pred.prob, t)) for name, t in thresholds]
    plot_matrices(panels, ["Melanoma", "No melanoma"], run / "matriz_confusion.png",
                  title=f"Matriz de confusión ({source})")

    tables, panels = [], []
    for name, t in thresholds:
        table = by_diagnosis(pred.dx, pred.prob, t)
        tables.append(table.assign(threshold=t))
        counts = np.column_stack([table.predicted_melanoma, table.images - table.predicted_melanoma])
        panels.append((name, counts))
    labels = [DIAGNOSES.get(d, d) for d in tables[0].index]
    plot_matrices(panels, labels, run / "matriz_por_diagnostico.png",
                  title=f"Predicción por diagnóstico de HAM10000 ({source})")
    pd.concat(tables).reset_index().to_csv(run / "matriz_por_diagnostico.csv", index=False,
                                           float_format="%.4f")
    print(f"Figuras en {run}")


if __name__ == "__main__":
    main()
