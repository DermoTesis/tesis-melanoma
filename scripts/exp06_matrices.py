"""Matrices de confusión de EXP-06: una foto, promedio de las dos y fusión aprendida.

    python scripts/exp06_matrices.py resultados/exp06/<corrida> [--degradaciones blur_8 dark_0.25]

Cada método usa su propio umbral con sensibilidad 90%, fijado con las fotos limpias (en los mismos
datos: optimista, solo para comparar). Genera en la carpeta de la corrida:
- matriz_confusion.png: las tres con fotos limpias;
- matriz_confusion_<degradación>.png: las tres con la foto A degradada y el MISMO umbral de las
  fotos limpias, como pasaría en producción (exploratorio, ver exp06_umbral_fijo.py);
- matriz_por_diagnostico.png y .csv: la fusión aprendida por diagnóstico de HAM10000.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from melanoma.figures import DIAGNOSES, by_diagnosis, confusion_table, plot_matrices
from melanoma.metrics import threshold_for_recall

METHODS = {"single_a": "Una foto", "average": "Promedio de las dos", "fusion": "Fusión aprendida"}
DEGRADATIONS = {"blur": "desenfoque", "dark": "poca luz"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("corrida", type=Path)
    parser.add_argument("--degradaciones", nargs="*", default=["blur_8", "dark_0.25"])
    args = parser.parse_args()

    run = args.corrida
    target = yaml.safe_load((run / "config.yaml").read_text())["metrics"]["target_recall"]
    pred = pd.read_csv(run / "predicciones_val.csv")
    y = pred.label.to_numpy()
    thresholds = {m: threshold_for_recall(y, pred[m].to_numpy(), target) for m in METHODS}
    source = f"EXP-06 · {len(pred):,} lesiones con 2 o más fotos"
    rows = ["Melanoma", "No melanoma"]

    panels = [(f"{name} (umbral {thresholds[m]:.3f})", confusion_table(y, pred[m], thresholds[m]))
              for m, name in METHODS.items()]
    plot_matrices(panels, rows, run / "matriz_confusion.png",
                  title=f"Matriz de confusión con sensibilidad {target:.0%} ({source})")

    for degradation in args.degradaciones:
        kind, level = degradation.split("_")
        panels = [(name, confusion_table(y, pred[f"{m}_{degradation}"], thresholds[m]))
                  for m, name in METHODS.items()]
        plot_matrices(panels, rows, run / f"matriz_confusion_{degradation}.png",
                      title=f"Foto A con {DEGRADATIONS[kind]} ({level}) y el umbral de las fotos "
                            f"limpias ({source})")

    table = by_diagnosis(pred.dx, pred.fusion, thresholds["fusion"])
    counts = np.column_stack([table.predicted_melanoma, table.images - table.predicted_melanoma])
    plot_matrices([(f"Fusión aprendida (umbral {thresholds['fusion']:.3f})", counts)],
                  [DIAGNOSES.get(d, d) for d in table.index], run / "matriz_por_diagnostico.png",
                  title=f"Predicción por diagnóstico ({source})")
    table.assign(threshold=thresholds["fusion"]).reset_index().to_csv(
        run / "matriz_por_diagnostico.csv", index=False, float_format="%.4f")
    print(f"Figuras en {run}")


if __name__ == "__main__":
    main()
