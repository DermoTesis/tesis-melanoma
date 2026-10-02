"""EXP-02: MobileNetV3-Large de extremo a extremo, una foto por imagen, en los 5 folds.

    python experiments/exp02_mobilenetv3.py
    python experiments/exp02_mobilenetv3.py --set "folds=[0]" --set data.max_images=300   # prueba

Por cada fold entrena en dos fases con los otros cuatro y predice su fold de validación; el test
no se toca. Reporta las métricas de cada fold, su media ± desviación y las métricas de todas las
predicciones fuera de fold juntas, con IC 95% por bootstrap de lesiones. Las predicciones quedan
en `resultados/` (las usa EXP-04) y los modelos en `outputs/`.
"""

from __future__ import annotations

import sys

from melanoma.config import parse_cli
from melanoma.runs import PROJECT_ROOT, start_run

CONFIG = PROJECT_ROOT / "configs" / "exp02_mobilenetv3.yaml"


def main(argv: list[str] | None = None) -> int:
    cfg, _ = parse_cli(__doc__.splitlines()[0], CONFIG, argv)
    # TensorFlow tarda en importar: después de validar los argumentos.
    import pandas as pd

    from melanoma.data import ham10000
    from melanoma.data.splits import load_splits
    from melanoma.metrics import cv_summary, evaluate, point_metrics
    from melanoma.training import setup_devices, train_fold_isolated

    devices = setup_devices(cfg["training"])
    print(f"GPU: {devices['gpus'] or 'ninguna'}; precisión mixta: {devices['mixed_precision']}; "
          f"XLA: {devices['jit_compile']}")

    splits = load_splits(PROJECT_ROOT / cfg["paths"]["splits"] / cfg["split"]["name"])
    images_dir = PROJECT_ROOT / cfg["data"]["sources"]["ham10000"]["images"]
    missing = ham10000.missing_images(splits, images_dir)
    if missing:
        raise FileNotFoundError(f"Faltan {len(missing)} imágenes en {images_dir}, p. ej. {missing[:3]}")

    target = cfg["metrics"]["target_recall"]
    op = f"s{round(target * 100)}"   # sufijo de las métricas con sensibilidad objetivo
    run = start_run(cfg, "exp02", cfg["model"]["backbone"])
    print(f"Corrida {run.run_id}")
    rows, predictions, training_info = [], [], {}
    for fold in cfg["folds"]:
        print(f"\n=== Fold {fold} ===")
        pred, info = train_fold_isolated(cfg, splits, fold, images_dir,
                                         run.artifacts_dir / f"fold_{fold}")
        predictions.append(pred)
        training_info[str(fold)] = info
        metrics = point_metrics(pred.label, pred.prob, target)
        rows.append({"model": cfg["model"]["backbone"], "fold": fold, **metrics,
                     "n_images": len(pred), "best_epoch": info["best_epoch"],
                     "train_seconds": info["train_seconds"]})
        print(f"Fold {fold}: AUC-ROC {metrics['auc_roc']:.4f}, PR-AUC {metrics['pr_auc']:.4f}, "
              f"especificidad con sensibilidad {target:.0%}: {metrics[f'specificity_{op}']:.4f} "
              f"(mejor época {info['best_epoch']}, {info['train_seconds']:.0f} s)")

    oof = pd.concat(predictions, ignore_index=True)
    oof.to_csv(run.results_dir / "predicciones_val.csv", index=False, float_format="%.6f")
    m = cfg["metrics"]
    pooled = evaluate(oof.label, oof.prob, oof.lesion_id, target, m["bootstrap_resamples"],
                      m["confidence_level"], cfg["seed"])
    summary = cv_summary(rows)
    rows.append({"model": cfg["model"]["backbone"], "fold": "oof", **pooled})

    run.save_metrics(rows, details={"cv": summary, "devices": devices, "training": training_info})
    auc = summary["auc_roc"]
    print(f"\nAUC-ROC por fold: {auc['mean']:.4f} ± {auc['std']:.4f}")
    print(f"AUC-ROC de todas las predicciones fuera de fold: {pooled['auc_roc']:.4f} "
          f"[{pooled['auc_roc_ci_low']:.4f}, {pooled['auc_roc_ci_high']:.4f}]")
    spec = f"specificity_{op}"
    print(f"Especificidad con sensibilidad {target:.0%}: {pooled[spec]:.4f} "
          f"[{pooled[spec + '_ci_low']:.4f}, {pooled[spec + '_ci_high']:.4f}]")
    print(f"Corrida registrada en {run.results_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
