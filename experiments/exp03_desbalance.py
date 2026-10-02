"""EXP-03: manejo del desbalance sobre el MobileNetV3-Large de EXP-02, en los 5 folds (HU15).

    python experiments/exp03_desbalance.py
    python experiments/exp03_desbalance.py --set "strategies=[focal_loss]"   # solo una

Cada estrategia (sin balanceo, pesos de clase, sobremuestreo y focal loss) es una corrida aparte
en `resultados/exp03/`, con la misma partición, semillas y entrenamiento que EXP-02: solo cambia
`training.imbalance`, que actúa únicamente sobre el entrenamiento. Si se corta, las estrategias
ya terminadas quedan guardadas.

Cada estrategia se compara con `none` sobre las mismas imágenes, con IC por bootstrap pareado de
lesiones. `none` se compara con la corrida de EXP-02 de `baseline_run`: como es el mismo
entrenamiento, esa diferencia muestra cuánto varía el resultado entre dos corridas iguales.

Criterio de elección, fijado antes de correr (HU15: sensibilidad y AUC-ROC, no exactitud):
- Se adopta la estrategia con mayor AUC-ROC fuera de fold solo si el IC de su diferencia con `none`
  queda por encima de 0 y su especificidad con sensibilidad 90% no empeora (el IC de esa diferencia
  no queda entero bajo 0). Esa especificidad es el costo de llegar a la sensibilidad obligatoria.
- Si ninguna cumple, se queda `none`: EXP-04 igual ajusta el umbral para la sensibilidad.
- La sensibilidad con umbral 0.5 se reporta, pero no decide: depende de la escala de las
  probabilidades, que cambia con cada estrategia y que EXP-04 recalibra.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

from melanoma.config import parse_cli
from melanoma.runs import PROJECT_ROOT, start_run

CONFIG = PROJECT_ROOT / "configs" / "exp03_desbalance.yaml"

# Lo que puede diferir de la corrida de referencia sin romper la comparación.
IGNORED = ("experiment", "paths.", "strategies", "baseline_run", "folds", "training.imbalance",
           "training.oversampling_positive_fraction", "training.focal_gamma")


def main(argv: list[str] | None = None) -> int:
    cfg, _ = parse_cli(__doc__.splitlines()[0], CONFIG, argv)
    import pandas as pd
    import yaml

    from melanoma.data import ham10000
    from melanoma.data.splits import load_splits
    from melanoma.imbalance import STRATEGIES
    from melanoma.metrics import compare_paired, cv_summary, evaluate, point_metrics
    from melanoma.training import setup_devices, train_fold_isolated

    unknown = [s for s in cfg["strategies"] if s not in STRATEGIES]
    if unknown:
        raise SystemExit(f"Estrategias desconocidas {unknown}; opciones: {list(STRATEGIES)}")
    strategies = sorted(cfg["strategies"], key=lambda s: s != "none")   # none primero

    baseline = None
    if cfg.get("baseline_run"):
        run_dir = PROJECT_ROOT / cfg["paths"]["results"] / cfg["baseline_run"]
        different = _differences(cfg, yaml.safe_load((run_dir / "config.yaml").read_text()))
        if different:
            raise SystemExit(f"La corrida {cfg['baseline_run']} no es comparable; difiere en: "
                             f"{', '.join(different)}. Usa --set baseline_run=null.")
        baseline = ("EXP-02 " + run_dir.name, pd.read_csv(run_dir / "predicciones_val.csv"))

    devices = setup_devices(cfg["training"])
    print(f"GPU: {devices['gpus'] or 'ninguna'}; precisión mixta: {devices['mixed_precision']}; "
          f"XLA: {devices['jit_compile']}")
    splits = load_splits(PROJECT_ROOT / cfg["paths"]["splits"] / cfg["split"]["name"])
    images_dir = PROJECT_ROOT / cfg["data"]["sources"]["ham10000"]["images"]
    missing = ham10000.missing_images(splits, images_dir)
    if missing:
        raise FileNotFoundError(f"Faltan {len(missing)} imágenes en {images_dir}, p. ej. {missing[:3]}")

    m = cfg["metrics"]
    target = m["target_recall"]
    op = f"s{round(target * 100)}"
    summary = []
    for strategy in strategies:
        cfg_s = copy.deepcopy(cfg)
        cfg_s["training"]["imbalance"] = strategy
        run = start_run(cfg_s, "exp03", strategy)
        print(f"\n##### Estrategia {strategy}: corrida {run.run_id}")
        rows, predictions, training_info = [], [], {}
        for fold in cfg["folds"]:
            print(f"\n=== {strategy}, fold {fold} ===")
            pred, info = train_fold_isolated(cfg_s, splits, fold, images_dir,
                                             run.artifacts_dir / f"fold_{fold}")
            predictions.append(pred)
            training_info[str(fold)] = info
            metrics = point_metrics(pred.label, pred.prob, target)
            rows.append({"model": cfg["model"]["backbone"], "strategy": strategy, "fold": fold,
                         **metrics, "n_images": len(pred), "best_epoch": info["best_epoch"],
                         "train_seconds": info["train_seconds"]})
            print(f"{strategy}, fold {fold}: AUC-ROC {metrics['auc_roc']:.4f}, especificidad con "
                  f"sensibilidad {target:.0%}: {metrics[f'specificity_{op}']:.4f}")

        oof = pd.concat(predictions, ignore_index=True)
        oof.to_csv(run.results_dir / "predicciones_val.csv", index=False, float_format="%.6f")
        pooled = evaluate(oof.label, oof.prob, oof.lesion_id, target, m["bootstrap_resamples"],
                          m["confidence_level"], cfg["seed"])
        reference = baseline
        if strategy != "none" and summary and summary[0]["strategy"] == "none":
            reference = summary[0]["reference_for_others"]
        if reference is not None:
            merged = oof.merge(reference[1][["image_id", "prob"]], on="image_id",
                               suffixes=("", "_ref"), validate="one_to_one")
            if len(merged) == len(oof):
                pooled.update(compare_paired(merged.label, merged.prob_ref, merged.prob,
                                             merged.lesion_id, target, m["bootstrap_resamples"],
                                             m["confidence_level"], cfg["seed"]))
                pooled["reference"] = reference[0]
            else:
                print(f"Aviso: {reference[0]} no tiene todas las imágenes; sin comparación pareada.")
        cv = cv_summary(rows)
        rows.append({"model": cfg["model"]["backbone"], "strategy": strategy, "fold": "oof",
                     **pooled})
        run.save_metrics(rows, details={"cv": cv, "devices": devices, "training": training_info})
        summary.append({"strategy": strategy, "pooled": pooled, "cv": cv,
                        "reference_for_others": (f"EXP-03 none {run.run_id}", oof)})
        print(f"Corrida registrada en {run.results_dir}")

    _print_summary(summary, target, op)
    return 0


def _flatten(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in d.items():
        if isinstance(value, dict):
            out.update(_flatten(value, f"{prefix}{key}."))
        else:
            out[f"{prefix}{key}"] = value
    return out


def _differences(cfg: dict[str, Any], other: dict[str, Any]) -> list[str]:
    a, b = _flatten(cfg), _flatten(other)
    keys = sorted(set(a) | set(b))
    return [k for k in keys if not k.startswith(IGNORED) and a.get(k) != b.get(k)]


def _print_summary(summary: list[dict[str, Any]], target: float, op: str) -> None:
    print(f"\n{'Estrategia':14s} {'AUC-ROC [IC 95%]':26s} {'ΔAUC [IC 95%]':26s} "
          f"{f'Espec. sens. {target:.0%}':24s} Sens. umbral 0.5")
    for s in summary:
        p = s["pooled"]
        auc = f"{p['auc_roc']:.4f} [{p['auc_roc_ci_low']:.4f}, {p['auc_roc_ci_high']:.4f}]"
        delta = (f"{p['delta_auc_roc']:+.4f} [{p['delta_auc_roc_ci_low']:+.4f}, "
                 f"{p['delta_auc_roc_ci_high']:+.4f}]" if "delta_auc_roc" in p else "—")
        spec = f"{p[f'specificity_{op}']:.4f}"
        if f"delta_specificity_{op}" in p:
            spec += f" ({p[f'delta_specificity_{op}']:+.4f})"
        print(f"{s['strategy']:14s} {auc:26s} {delta:26s} {spec:24s} {p['recall_t50']:.4f}")
    print("Δ: diferencia pareada con none (y la de none, con EXP-02).")


if __name__ == "__main__":
    sys.exit(main())
