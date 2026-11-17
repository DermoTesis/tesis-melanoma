"""EXP-10: el modelo de una foto entrenado con fotos degradadas, frente a la fusión (ablación de la H3).

    python experiments/exp10_una_foto_degradada.py
    python experiments/exp10_una_foto_degradada.py --set resume=exp10/<id>   # retoma una corrida
    python experiments/exp10_una_foto_degradada.py --set "folds=[0]" --set data.max_images=64 \\
        --set pairs.max_lesions=16 --set training.phases.head.epochs=1 \\
        --set training.phases.finetune.epochs=1                                # prueba

Motivo: en EXP-06 (y en el test, H3) la fusión mantiene la sensibilidad cuando una foto está
degradada y el promedio no. Pero solo la fusión se entrenó con fotos degradadas. Este experimento
separa las dos explicaciones: ¿la robustez viene de ponderar las fotos o solo de haber visto fotos
malas al entrenar? Lo pidió el short paper (PENDING de V-B).

Diseño:
- El modelo de una foto de EXP-03 (MobileNetV3-Large, sin balanceo, mismas semillas, épocas y
  folds), pero cada imagen de entrenamiento llega degradada con probabilidad 0.15, con los mismos
  tipos y niveles que la fusión: desenfoque σ ∈ {1.5, 3, 5} o brillo × [0.3, 0.7]. 0.15 es la
  proporción de fotos degradadas que vio la fusión (30% de los pares, una de sus dos fotos).
- Con el modelo de cada fold se predicen los mismos pares fijos (A, B) de EXP-06 (semilla 42 +
  fold), con la foto A limpia y con las 5 degradaciones de evaluación. "Promedio robusto" es el
  promedio de las dos predicciones de este modelo.
- Se compara con la fusión y con el promedio de EXP-06 sobre las mismas 1,662 lesiones.
- Umbrales: los de sensibilidad 90% con fotos limpias, cada uno sobre sus propias predicciones
  fuera de fold, como el análisis exploratorio de EXP-06.

Criterio, fijado antes de correr:
- Principal: Δ = sensibilidad de la fusión − sensibilidad del promedio robusto, con la foto A
  degradada y los umbrales de fotos limpias; se promedia sobre las 5 degradaciones, con IC 95% por
  bootstrap pareado de lesiones (como la H3).
  - Si el IC queda entero sobre 0: la robustez de la fusión no se explica solo por haber visto
    fotos degradadas.
  - Si no, se mira la especificidad con las mismas degradaciones y umbrales (Δ de especificidad,
    fusión − promedio robusto, promediada sobre las 5, con su IC):
    - si su IC no queda entero sobre 0, entrenar el modelo de una foto con fotos degradadas basta
      para que el promedio sea igual de robusto, y el paper lo dice así;
    - si queda entero sobre 0, el promedio robusto mantiene la sensibilidad a costa de
      especificidad: no concluyente.
- Secundario: el costo de entrenar con degradaciones, como la ΔAUC-ROC del modelo de una foto con
  fotos limpias frente a EXP-03 (8,512 imágenes), con IC pareado; también la especificidad de cada
  método con las degradaciones.
- No cambia el modelo final ni toca el test (ya evaluado).

Si se corta, se retoma con `--set resume=exp10/<id>`: cada fold terminado queda en
`outputs/exp10/<id>/fold_<k>/` y no se repite.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from melanoma.config import parse_cli
from melanoma.runs import PROJECT_ROOT, reopen_run, start_run

CONFIG = PROJECT_ROOT / "configs" / "exp10_una_foto_degradada.yaml"
METHODS = ("fusion", "average", "robust_average")   # fusión y promedio de EXP-06; promedio nuevo


def is_done(directory: Path) -> bool:
    return all((directory / f).is_file() for f in ("predicciones.csv", "pares.csv", "info.json"))


def main(argv: list[str] | None = None) -> int:
    cfg, _ = parse_cli(__doc__.splitlines()[0], CONFIG, argv)
    from melanoma.data import ham10000
    from melanoma.data.splits import load_splits
    from melanoma.training import setup_devices

    devices = setup_devices(cfg["training"])
    print(f"GPU: {devices['gpus'] or 'ninguna'}; precisión mixta: {devices['mixed_precision']}; "
          f"XLA: {devices['jit_compile']}")
    splits = load_splits(PROJECT_ROOT / cfg["paths"]["splits"] / cfg["split"]["name"])
    images_dir = PROJECT_ROOT / cfg["data"]["sources"]["ham10000"]["images"]
    missing = ham10000.missing_images(splits, images_dir)
    if missing:
        raise FileNotFoundError(f"Faltan {len(missing)} imágenes en {images_dir}, p. ej. {missing[:3]}")

    if cfg.get("resume"):
        run = reopen_run(cfg, cfg["resume"])
        print(f"Se retoma la corrida {cfg['resume']}")
    else:
        run = start_run(cfg, cfg["experiment"], "una-foto-degradada")
        print(f"Corrida exp10/{run.run_id}. Si se corta: --set resume=exp10/{run.run_id}")

    for fold in cfg["folds"]:
        out_dir = run.artifacts_dir / f"fold_{fold}"
        if is_done(out_dir):
            print(f"Fold {fold}: ya está hecho")
            continue
        _train(cfg, splits, images_dir, fold, out_dir)
    analyze(cfg, run, devices)
    return 0


def _train(cfg, splits, images_dir: Path, fold: int, out_dir: Path) -> None:
    from melanoma.multiview import single_view_pairs
    from melanoma.training import run_isolated, train_fold_isolated

    if out_dir.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir.rename(out_dir.with_name(f"{out_dir.name}.interrumpido-{stamp}"))
    print(f"\n=== Fold {fold} ===")
    start = time.perf_counter()
    pred, info = train_fold_isolated(cfg, splits, fold, images_dir, out_dir)
    pairs = run_isolated(single_view_pairs, cfg, splits, fold, images_dir, out_dir / "modelo.keras")
    info.update(wall_seconds=round(time.perf_counter() - start, 1),
                max_epochs=sum(p["epochs"] for p in cfg["training"]["phases"].values()))
    (out_dir / "info.json").write_text(json.dumps(info, default=_jsonable, ensure_ascii=False),
                                       encoding="utf-8")
    pairs.to_csv(out_dir / "pares.csv", index=False, float_format="%.6f")
    tmp = out_dir / "predicciones.csv.tmp"
    pred.to_csv(tmp, index=False, float_format="%.6f")
    tmp.rename(out_dir / "predicciones.csv")        # al final: marca el fold como terminado
    print(f"Fold {fold} terminado en {info['wall_seconds'] / 60:.1f} min (mejor época "
          f"{info['best_epoch']} de {info['max_epochs']})")


def _jsonable(obj: Any) -> Any:
    if hasattr(obj, "tolist"):
        return obj.tolist()
    raise TypeError(f"No se puede serializar {type(obj).__name__}")


def merge_with_exp06(new_pairs, exp06):
    """Une por lesión y par (A, B): si los pares no son exactamente los de EXP-06, se detiene."""
    keys = ["lesion_id", "image_a", "image_b", "label"]
    robust = new_pairs[keys + [c for c in new_pairs if c.startswith(("single_", "average"))]]
    robust = robust.rename(columns=lambda c: c if c in keys else
                           c.replace("single_", "robust_single_").replace("average", "robust_average"))
    both = exp06.merge(robust, on=keys, how="inner", validate="one_to_one")
    if len(both) != len(new_pairs):
        raise SystemExit("Los pares de validación no coinciden con los de EXP-06")
    return both


def robustness(y, groups, scores: dict[str, Any], names: list[str], thresholds: dict[str, float],
               boot: tuple[int, float, int], a: str, b: str, metric: str = "recall") -> dict[str, Any]:
    """Δ de `metric` (a − b) con la foto A degradada, por degradación y promediada, con IC."""
    import numpy as np

    from melanoma.metrics import at_threshold, bootstrap_indices

    def deltas(idx):
        return [at_threshold(y[idx], scores[f"{a}_{n}"][idx], thresholds[a])[metric]
                - at_threshold(y[idx], scores[f"{b}_{n}"][idx], thresholds[b])[metric] for n in names]

    point = deltas(np.arange(len(y)))
    samples = np.array([deltas(i) for i in bootstrap_indices(groups, boot[0], boot[2])])
    alpha = (1 - boot[1]) / 2
    return {"metric": metric, "mean_delta": float(np.mean(point)),
            "ci_low": float(np.quantile(samples.mean(axis=1), alpha)),
            "ci_high": float(np.quantile(samples.mean(axis=1), 1 - alpha)),
            "by_degradation": {n: {"delta": point[j],
                                   "ci_low": float(np.quantile(samples[:, j], alpha)),
                                   "ci_high": float(np.quantile(samples[:, j], 1 - alpha))}
                               for j, n in enumerate(names)}}


def analyze(cfg: dict[str, Any], run, devices: dict[str, Any]) -> None:
    import pandas as pd

    from melanoma.metrics import at_threshold, compare_paired, threshold_for_recall
    from melanoma.multiview import degradations

    m = cfg["metrics"]
    target = m["target_recall"]
    boot = (m["bootstrap_resamples"], m["confidence_level"], cfg["seed"])
    results = PROJECT_ROOT / cfg["paths"]["results"]
    folds = [run.artifacts_dir / f"fold_{f}" for f in cfg["folds"]]

    # Secundario: costo con fotos limpias, sobre las mismas imágenes que EXP-03.
    single = pd.concat([pd.read_csv(d / "predicciones.csv") for d in folds], ignore_index=True)
    ref = pd.read_csv(results / cfg["single_view_run"] / "predicciones_val.csv")[["image_id", "prob"]]
    single = single.merge(ref.rename(columns={"prob": "exp03"}), on="image_id", validate="one_to_one")
    cost = compare_paired(single.label, single.exp03, single.prob, single.lesion_id, target, *boot)

    # Principal: pares de EXP-06.
    exp06 = pd.read_csv(results / cfg["two_view_run"] / "predicciones_val.csv")
    new_pairs = pd.concat([pd.read_csv(d / "pares.csv") for d in folds], ignore_index=True)
    both = merge_with_exp06(new_pairs, exp06)
    both.to_csv(run.results_dir / "predicciones_pares.csv", index=False, float_format="%.6f")
    y, groups = both.label.to_numpy(), both.lesion_id.to_numpy()
    names = [n for n, _, _ in degradations(cfg)]
    scores = {c: both[c].to_numpy() for c in both.columns if c.startswith(METHODS)}
    thresholds = {k: threshold_for_recall(y, scores[k], target) for k in METHODS}
    main_test = robustness(y, groups, scores, names, thresholds, boot, "fusion", "robust_average")
    spec_test = robustness(y, groups, scores, names, thresholds, boot, "fusion", "robust_average",
                           metric="specificity")
    vs_old = robustness(y, groups, scores, names, thresholds, boot, "robust_average", "average")

    table = {}
    for k in METHODS:
        table[k] = {"clean": {**at_threshold(y, scores[k], thresholds[k]),
                              "auc_roc": _auc(y, scores[k])}}
        for n in names:
            table[k][n] = {**at_threshold(y, scores[f"{k}_{n}"], thresholds[k]),
                           "auc_roc": _auc(y, scores[f"{k}_{n}"])}
    if main_test["ci_low"] > 0:
        verdict = "la robustez de la fusión no se explica solo por ver fotos degradadas"
    elif spec_test["ci_low"] > 0:
        verdict = "no concluyente: el promedio robusto mantiene la sensibilidad a costa de especificidad"
    else:
        verdict = "entrenar con fotos degradadas basta para que el promedio sea igual de robusto"
    rows = [{"method": k, "condition": c, **v} for k, conds in table.items() for c, v in conds.items()]
    for test in (main_test, spec_test):
        rows.append({"method": "fusion - robust_average", "condition": "media de las 5 degradaciones",
                     **{k: v for k, v in test.items() if k != "by_degradation"}})
    run.save_metrics(rows, details={"devices": devices, "thresholds": thresholds, "verdict": verdict,
                                    "fusion_minus_robust_average": main_test,
                                    "fusion_minus_robust_average_specificity": spec_test,
                                    "robust_average_minus_average": vs_old,
                                    "clean_single_view_cost": cost})
    print(f"\nCosto con fotos limpias (una foto, frente a EXP-03): ΔAUC {cost['delta_auc_roc']:+.4f} "
          f"[{cost['delta_auc_roc_ci_low']:+.4f}, {cost['delta_auc_roc_ci_high']:+.4f}]")
    print(f"{'Condición':12s} " + "  ".join(f"{k:>22s}" for k in METHODS) + "   (sens / esp)")
    for c in ["clean"] + names:
        print(f"{c:12s} " + "  ".join(f"{table[k][c]['recall'] * 100:10.1f} / "
                                     f"{table[k][c]['specificity'] * 100:5.1f}     " for k in METHODS))
    for t, label in ((main_test, "sensibilidad"), (spec_test, "especificidad")):
        print(f"Δ {label} fusión − promedio robusto (media de 5): {t['mean_delta']:+.3f} "
              f"[{t['ci_low']:+.3f}, {t['ci_high']:+.3f}]")
    print(f"→ {verdict}")
    print(f"Corrida registrada en {run.results_dir}")


def _auc(y, p) -> float:
    from sklearn.metrics import roc_auc_score

    return float(roc_auc_score(y, p))


if __name__ == "__main__":
    sys.exit(main())
