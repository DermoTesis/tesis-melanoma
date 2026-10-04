"""Análisis EXPLORATORIO de EXP-06: robustez con el umbral operativo fijo.

    python scripts/exp06_umbral_fijo.py resultados/exp06/<corrida>

El criterio de EXP-06 midió la H3 con AUC y con la especificidad en un umbral recalculado para
cada condición. Ninguna de las dos ve lo que pasa en producción: el umbral se fija con fotos
buenas y queda fijo, así que si una foto mala corre las probabilidades, cambia la sensibilidad.
Este análisis fija, para cada método, el umbral con sensibilidad 90% en las fotos limpias y lo
aplica con la foto A degradada. No estaba en el criterio fijado antes de correr: se reporta como
exploratorio y se propone confirmarlo en el test (EXP-04).

Guarda `umbral_fijo.json` en la carpeta de la corrida.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from melanoma.metrics import at_threshold, threshold_for_recall

METHODS = ("single_a", "average", "fusion")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("corrida", type=Path)
    parser.add_argument("--remuestreos", type=int, default=2000)
    args = parser.parse_args()

    cfg = yaml.safe_load((args.corrida / "config.yaml").read_text())
    target = cfg["metrics"]["target_recall"]
    pred = pd.read_csv(args.corrida / "predicciones_val.csv")
    y = pred.label.to_numpy()
    names = [f"{kind}_{level:g}" for kind, levels in cfg["evaluation_degradations"].items()
             for level in levels]
    thresholds = {m: threshold_for_recall(y, pred[m].to_numpy(), target) for m in METHODS}

    def operating(m: str, column: str, idx: np.ndarray) -> dict[str, float]:
        return at_threshold(y[idx], pred[column].to_numpy()[idx], thresholds[m])

    everything = np.arange(len(y))
    out = {"target_recall": target, "thresholds": thresholds, "conditions": {}}
    rng = np.random.default_rng(cfg["seed"])
    samples = [rng.integers(0, len(y), len(y)) for _ in range(args.remuestreos)]   # 1 fila = 1 lesión
    for condition in ["limpia", *names]:
        suffix = "" if condition == "limpia" else f"_{condition}"
        result = {m: {k: operating(m, m + suffix, everything)[k] for k in ("recall", "specificity")}
                  for m in METHODS}
        if condition != "limpia":
            diffs = [operating("fusion", "fusion" + suffix, i)["recall"]
                     - operating("average", "average" + suffix, i)["recall"] for i in samples]
            result["delta_recall_fusion_minus_average"] = {
                "point": result["fusion"]["recall"] - result["average"]["recall"],
                "ci_low": float(np.quantile(diffs, 0.025)), "ci_high": float(np.quantile(diffs, 0.975))}
        out["conditions"][condition] = result

    (args.corrida / "umbral_fijo.json").write_text(json.dumps(out, indent=2) + "\n")
    print(f"{'Condición':10s}" + "".join(f"{m:>24s}" for m in METHODS) + "   Δsens fusión − promedio")
    for condition, r in out["conditions"].items():
        line = f"{condition:10s}" + "".join(
            f"   sens {r[m]['recall']:.3f} esp {r[m]['specificity']:.3f}" for m in METHODS)
        if "delta_recall_fusion_minus_average" in r:
            d = r["delta_recall_fusion_minus_average"]
            line += f"   {d['point']:+.3f} [{d['ci_low']:+.3f}, {d['ci_high']:+.3f}]"
        print(line)


if __name__ == "__main__":
    main()
