"""EXP-09: validación dejando fuera una fuente de HAM10000 (leave-one-source-out), una foto.

    python experiments/exp09_fuentes.py
    python experiments/exp09_fuentes.py --set resume=exp09/<id>        # retoma una corrida cortada
    python experiments/exp09_fuentes.py --set data.max_images=64 \\
        --set training.phases.head.epochs=1 --set training.phases.finetune.epochs=1   # prueba

Motivo: dentro de cada fuente, la AUC-ROC fuera de fold (0.775 a 0.853) es menor que la global
(0.884), así que parte del desempeño global viene de diferencias entre fuentes. Este experimento
mide cómo rinde el modelo con una fuente que nunca vio, lo más parecido a otro equipo de captura
que se puede hacer con HAM10000. Lo pidió el short paper (PENDING de V-A).

Diseño:
- Solo train+val (8,512 imágenes); el test no entra.
- Para cada fuente s (rosendahl, vidir_modern, vidir_molemax, vienna_dias):
  - entrena el modelo de una foto (MobileNetV3-Large, sin balanceo, como EXP-03) con las imágenes
    de las otras tres fuentes, salvo las del fold `early_stopping_fold`, que detienen el
    entrenamiento (parada temprana por AUC, como siempre);
  - predice todas las imágenes de train+val de la fuente s.
- La semilla es `seed` + el índice de la fuente. El resto de la configuración es la de EXP-03.
- Referencia: las predicciones fuera de fold de EXP-03 sin balanceo sobre las mismas imágenes de
  s. Esos modelos entrenaron con el 80% de todas las fuentes, incluida s.

Criterio, fijado antes de correr. Es descriptivo, porque no cambia el modelo ni el test, que ya se
evaluó:
- por fuente se reporta la AUC-ROC dejando la fuente fuera y la AUC-ROC fuera de fold dentro de la
  fuente, con IC 95% por bootstrap de lesiones, y su diferencia pareada (fuera − dentro);
- si el IC de la diferencia queda entero bajo 0, el modelo pierde discriminación con esa fuente
  cuando no la vio al entrenar, o sea que depende de rasgos propios de la fuente;
- vidir_molemax tiene solo 20 melanomas en train+val: su IC será muy ancho y no se interpreta solo;
- también se reporta la AUC-ROC de las 4 fuentes juntas, cada una predicha por el modelo que no la
  vio, frente a la global fuera de fold (0.884).

Si se corta, se retoma con `--set resume=exp09/<id>`: cada fuente terminada queda en
`outputs/exp09/<id>/<fuente>/` y no se repite.
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

CONFIG = PROJECT_ROOT / "configs" / "exp09_fuentes.yaml"


def source_frames(splits, source: str, early_stopping_fold: int):
    """(entrenamiento, parada temprana, evaluación) dejando fuera `source`. El test nunca entra."""
    from melanoma.data.splits import TRAINVAL

    trainval = splits[splits.split == TRAINVAL]
    others = trainval[trainval.dataset != source]
    train = others[others.fold != early_stopping_fold]
    stop = others[others.fold == early_stopping_fold]
    held_out = trainval[trainval.dataset == source]
    return train, stop, held_out


def is_done(directory: Path) -> bool:
    return (directory / "predicciones.csv").is_file() and (directory / "info.json").is_file()


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
    unknown = set(cfg["sources"]) - set(splits.dataset)
    if unknown:
        raise SystemExit(f"Fuentes desconocidas: {sorted(unknown)}")

    if cfg.get("resume"):
        run = reopen_run(cfg, cfg["resume"])
        print(f"Se retoma la corrida {cfg['resume']}")
    else:
        run = start_run(cfg, cfg["experiment"], "fuentes")
        print(f"Corrida exp09/{run.run_id}. Si se corta: --set resume=exp09/{run.run_id}")

    for k, source in enumerate(cfg["sources"]):
        out_dir = run.artifacts_dir / source
        if is_done(out_dir):
            print(f"{source}: ya está hecha")
            continue
        _train(cfg, splits, images_dir, source, cfg["seed"] + k, out_dir)
    analyze(cfg, run, devices)
    return 0


def _train(cfg, splits, images_dir: Path, source: str, seed: int, out_dir: Path) -> None:
    from melanoma.data.pipeline import limit_images
    from melanoma.training import run_isolated, train_frames

    if out_dir.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir.rename(out_dir.with_name(f"{out_dir.name}.interrumpido-{stamp}"))
    train, stop, held_out = source_frames(splits, source, cfg["early_stopping_fold"])
    max_images = cfg["data"].get("max_images")
    train, stop, held_out = (limit_images(df, max_images, seed) for df in (train, stop, held_out))
    print(f"\n=== Fuera: {source} ({len(held_out)} imágenes, {int(held_out.label.sum())} melanomas); "
          f"entrena con {len(train)} y se detiene con {len(stop)} ===")
    start = time.perf_counter()
    pred, info = run_isolated(train_frames, cfg, train, stop, images_dir, out_dir, seed,
                              eval_df=held_out)
    info.update(wall_seconds=round(time.perf_counter() - start, 1), source=source, seed=seed,
                n_stop_images=int(len(stop)), n_held_out_images=int(len(held_out)),
                max_epochs=sum(p["epochs"] for p in cfg["training"]["phases"].values()))
    (out_dir / "info.json").write_text(json.dumps(info, default=_jsonable, ensure_ascii=False),
                                       encoding="utf-8")
    tmp = out_dir / "predicciones.csv.tmp"
    pred.assign(dataset=source).to_csv(tmp, index=False, float_format="%.6f")
    tmp.rename(out_dir / "predicciones.csv")
    print(f"{source}: terminada en {info['wall_seconds'] / 60:.1f} min (mejor época "
          f"{info['best_epoch']} de {info['max_epochs']})")


def _jsonable(obj: Any) -> Any:
    if hasattr(obj, "tolist"):
        return obj.tolist()
    raise TypeError(f"No se puede serializar {type(obj).__name__}")


def analyze(cfg: dict[str, Any], run, devices: dict[str, Any]) -> None:
    import pandas as pd

    from melanoma.metrics import compare_paired, evaluate

    m = cfg["metrics"]
    boot = (m["target_recall"], m["bootstrap_resamples"], m["confidence_level"], cfg["seed"])
    reference = pd.read_csv(PROJECT_ROOT / cfg["paths"]["results"] / cfg["reference_run"]
                            / "predicciones_val.csv")[["image_id", "prob"]].rename(
        columns={"prob": "within"})
    held = pd.concat([pd.read_csv(run.artifacts_dir / s / "predicciones.csv") for s in cfg["sources"]],
                     ignore_index=True).rename(columns={"prob": "left_out"})
    both = held.merge(reference, on="image_id", how="left", validate="one_to_one")
    if both.within.isna().any():
        raise SystemExit("Hay imágenes sin predicción fuera de fold en la corrida de referencia")
    both.to_csv(run.results_dir / "predicciones_fuentes.csv", index=False, float_format="%.6f")

    rows, details = [], {"devices": devices, "sources": {}}
    groups = {**{s: both[both.dataset == s] for s in cfg["sources"]}, "todas": both}
    for name, df in groups.items():
        y, g = df.label.to_numpy(), df.lesion_id.to_numpy()
        out = evaluate(y, df.left_out, g, *boot)
        within = evaluate(y, df.within, g, *boot)
        delta = compare_paired(y, df.within, df.left_out, g, *boot, keys=("auc_roc",))
        row = {"source": name, "n_images": int(len(df)), "n_melanoma": int(y.sum()),
               "auc_left_out": out["auc_roc"], "auc_left_out_ci_low": out["auc_roc_ci_low"],
               "auc_left_out_ci_high": out["auc_roc_ci_high"], "auc_within": within["auc_roc"],
               "auc_within_ci_low": within["auc_roc_ci_low"],
               "auc_within_ci_high": within["auc_roc_ci_high"], **delta,
               "depends_on_source": bool(delta["delta_auc_roc_ci_high"] < 0)}
        rows.append(row)
        details["sources"][name] = {"left_out": out, "within": within}
        print(f"{name:14s} n={len(df):5d} mel={int(y.sum()):4d}  fuera {out['auc_roc']:.3f} "
              f"[{out['auc_roc_ci_low']:.3f}, {out['auc_roc_ci_high']:.3f}]  dentro "
              f"{within['auc_roc']:.3f}  Δ {delta['delta_auc_roc']:+.4f} "
              f"[{delta['delta_auc_roc_ci_low']:+.4f}, {delta['delta_auc_roc_ci_high']:+.4f}]")
    run.save_metrics(rows, details=details)
    print(f"Corrida registrada en {run.results_dir}")


if __name__ == "__main__":
    sys.exit(main())
