"""EXP-11: cuánto se pierde con MobileNetV3-Large: backbones más grandes, AUC-ROC y latencia en CPU.

    python experiments/exp11_backbones.py                                  # entrenar (GPU)
    python experiments/exp11_backbones.py --set resume=exp11/<id>          # retoma el entrenamiento
    python experiments/exp11_backbones.py --set stage=latencia --set source_run=exp11/<id>   # CPU
    python experiments/exp11_backbones.py --set "folds=[0]" --set data.max_images=64 \\
        --set training.phases.head.epochs=1 --set training.phases.finetune.epochs=1   # prueba

Motivo: el modelo usa MobileNetV3-Large para que la inferencia sea barata en CPU (Cloud Run sin
GPU), pero no se midió cuánta discriminación cuesta esa elección. Lo pidió el short paper (PENDING
de VI-D: "AUC-ROC versus latency comparison").

Diseño:
- Modelo de una foto, sin balanceo, con la misma partición, semillas, aumento de datos y épocas
  que EXP-03 (5 + hasta 20, parada temprana de 5). Solo cambia el backbone:
  - EfficientNetV2-B0 (7 M de parámetros), de tamaño parecido;
  - EfficientNetV2-S (21 M), bastante más grande.
  Los dos traen su preprocesamiento y reciben píxeles 0-255, como MobileNetV3. Las tasas de
  aprendizaje no se ajustan para cada uno: es la misma receta, y eso favorece algo a MobileNetV3.
- Referencia: MobileNetV3-Large de EXP-03 sin balanceo, sobre las mismas 8,512 imágenes.
- Latencia (stage=latencia, en el contenedor de desarrollo, como EXP-05): modelo del fold 0 de
  cada backbone y de MobileNetV3, convertido a .tflite float16; tamaño del archivo y p50/p95 de
  una foto y de un caso de 2 fotos, en un proceso limitado a 2 núcleos.

Criterio, fijado antes de correr. Es descriptivo: el test ya se evaluó con MobileNetV3, así que
el modelo no cambia; esto cuantifica el costo de la elección.
- Por backbone: AUC-ROC fuera de fold con IC 95% por bootstrap de lesiones y ΔAUC-ROC pareada
  frente a MobileNetV3 (IC sobre 0 = discrimina mejor), más la especificidad con sensibilidad 90%.
- Un backbone "habría sido preferible" si su ΔAUC-ROC tiene el IC sobre 0 y el p95 de un caso de
  2 fotos queda bajo `max_p95_ms_case` (100 ms, el umbral de EXP-05).

Si el entrenamiento se corta, se retoma con `--set resume=exp11/<id>`: cada fold terminado queda
en `outputs/exp11/<id>/<backbone>/fold_<k>/` y no se repite.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from melanoma.config import deep_merge, parse_cli
from melanoma.runs import PROJECT_ROOT, reopen_run, start_run

CONFIG = PROJECT_ROOT / "configs" / "exp11_backbones.yaml"
REFERENCE = "mobilenet_v3_large"
EXPERIMENT_KEYS = ("backbones", "stage", "folds", "resume", "source_run", "reference_run",
                   "benchmark", "max_p95_ms_case")


def backbone_config(cfg: dict[str, Any], name: str) -> dict[str, Any]:
    """La configuración con la que entrena un fold: la base, con el backbone y sus cambios."""
    out = deep_merge({k: v for k, v in cfg.items() if k not in EXPERIMENT_KEYS},
                     cfg["backbones"][name] or {})
    out["model"] = {**out["model"], "backbone": name}
    return out


def fold_dir(artifacts: Path, name: str, fold: int) -> Path:
    return artifacts / name / f"fold_{fold}"


def is_done(directory: Path) -> bool:
    return (directory / "predicciones.csv").is_file() and (directory / "info.json").is_file()


def main(argv: list[str] | None = None) -> int:
    cfg, _ = parse_cli(__doc__.splitlines()[0], CONFIG, argv)
    if cfg["stage"] == "latencia":
        return latency(cfg)
    if cfg["stage"] != "entrenar":
        raise SystemExit("stage debe ser entrenar o latencia")
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
        run = start_run(cfg, cfg["experiment"], "backbones")
        print(f"Corrida exp11/{run.run_id}. Si se corta: --set resume=exp11/{run.run_id}")

    for name in cfg["backbones"]:
        for fold in cfg["folds"]:
            out_dir = fold_dir(run.artifacts_dir, name, fold)
            if not is_done(out_dir):
                _train(cfg, splits, images_dir, name, fold, out_dir)
    analyze(cfg, run, devices)
    return 0


def _train(cfg, splits, images_dir: Path, name: str, fold: int, out_dir: Path) -> None:
    from melanoma.training import train_fold_isolated

    if out_dir.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir.rename(out_dir.with_name(f"{out_dir.name}.interrumpido-{stamp}"))
    print(f"\n=== {name}, fold {fold} ===")
    bcfg = backbone_config(cfg, name)
    start = time.perf_counter()
    pred, info = train_fold_isolated(bcfg, splits, fold, images_dir, out_dir)
    info.update(wall_seconds=round(time.perf_counter() - start, 1),
                max_epochs=sum(p["epochs"] for p in bcfg["training"]["phases"].values()))
    (out_dir / "info.json").write_text(json.dumps(info, default=_jsonable, ensure_ascii=False),
                                       encoding="utf-8")
    tmp = out_dir / "predicciones.csv.tmp"
    pred.to_csv(tmp, index=False, float_format="%.6f")
    tmp.rename(out_dir / "predicciones.csv")
    print(f"{name}, fold {fold}: {info['wall_seconds'] / 60:.1f} min (mejor época {info['best_epoch']} "
          f"de {info['max_epochs']})")


def _jsonable(obj: Any) -> Any:
    if hasattr(obj, "tolist"):
        return obj.tolist()
    raise TypeError(f"No se puede serializar {type(obj).__name__}")


def analyze(cfg: dict[str, Any], run, devices: dict[str, Any]) -> None:
    import pandas as pd

    from melanoma.metrics import compare_paired, evaluate

    m = cfg["metrics"]
    boot = (m["target_recall"], m["bootstrap_resamples"], m["confidence_level"], cfg["seed"])
    op = f"s{round(m['target_recall'] * 100)}"
    wide = pd.read_csv(PROJECT_ROOT / cfg["paths"]["results"] / cfg["reference_run"]
                       / "predicciones_val.csv").rename(columns={"prob": REFERENCE})
    for name in cfg["backbones"]:
        df = pd.concat([pd.read_csv(fold_dir(run.artifacts_dir, name, f) / "predicciones.csv")
                        for f in cfg["folds"]], ignore_index=True)
        wide = wide.merge(df[["image_id", "prob"]].rename(columns={"prob": name}), on="image_id",
                          how="inner", validate="one_to_one")
    wide.to_csv(run.results_dir / "predicciones_val.csv", index=False, float_format="%.6f")
    y, g = wide.label.to_numpy(), wide.lesion_id.to_numpy()
    rows, details = [], {"devices": devices, "training": {}}
    for name in [REFERENCE, *cfg["backbones"]]:
        e = evaluate(y, wide[name], g, *boot)
        row = {"backbone": name, "fold": "oof", **e}
        if name != REFERENCE:
            row.update(compare_paired(y, wide[REFERENCE], wide[name], g, *boot))
            details["training"][name] = {
                str(f): json.loads((fold_dir(run.artifacts_dir, name, f) / "info.json").read_text())
                .get("best_epoch") for f in cfg["folds"]}
        rows.append(row)
        print(f"{name:20s} AUC {e['auc_roc']:.4f} [{e['auc_roc_ci_low']:.4f}, {e['auc_roc_ci_high']:.4f}]"
              f"  esp. {op} {e[f'specificity_{op}']:.3f}"
              + (f"  ΔAUC {row['delta_auc_roc']:+.4f} [{row['delta_auc_roc_ci_low']:+.4f}, "
                 f"{row['delta_auc_roc_ci_high']:+.4f}]" if name != REFERENCE else "  (referencia)"))
    run.save_metrics(rows, details=details)
    print(f"Corrida registrada en {run.results_dir}. Falta la latencia en CPU: "
          f"--set stage=latencia --set source_run=exp11/{run.run_id}")


def latency(cfg: dict[str, Any]) -> int:
    """Tamaño y latencia del .tflite float16 de cada backbone (fold 0), limitado a 2 núcleos."""
    from concurrent.futures import ProcessPoolExecutor
    from multiprocessing import get_context

    from melanoma.data.splits import load_splits, train_val
    from melanoma.export_tflite import benchmark, convert, load_trained

    if not cfg.get("source_run"):
        raise SystemExit("Falta --set source_run=exp11/<id> (la corrida de entrenamiento)")
    source = PROJECT_ROOT / cfg["paths"]["outputs"] / cfg["source_run"]
    results = PROJECT_ROOT / cfg["paths"]["results"]
    metrics = json.loads((results / cfg["source_run"] / "metricas.json").read_text())
    auc = {r["backbone"]: r for r in metrics["rows"]}
    run = start_run(cfg, cfg["experiment"], "latencia")
    size, bench = cfg["data"]["image_size"], cfg["benchmark"]
    splits = load_splits(PROJECT_ROOT / cfg["paths"]["splits"] / cfg["split"]["name"])
    images_dir = PROJECT_ROOT / cfg["data"]["sources"]["ham10000"]["images"]
    _, val = train_val(splits, 0)
    jpegs = [(images_dir / f"{i}.jpg").read_bytes()
             for i in sorted(val.image_id)[:bench["images"]]]
    models = {REFERENCE: PROJECT_ROOT / cfg["paths"]["outputs"] / cfg["reference_run"] / "fold_0"
              / "modelo.keras",
              **{name: fold_dir(source, name, 0) / "modelo.keras" for name in cfg["backbones"]}}
    rows = []
    for name, path in models.items():
        model = load_trained(path, {**cfg["model"], "backbone": name}, size)
        tflite = run.artifacts_dir / f"{name}_float16.tflite"
        tflite.write_bytes(convert(model, "float16"))
        with ProcessPoolExecutor(max_workers=1, mp_context=get_context("spawn")) as pool:
            lat = pool.submit(benchmark, tflite, jpegs, size, bench["threads"], bench["warmup_runs"],
                              bench["timed_runs"], 4).result()
        a = auc.get(name, {})
        row = {"backbone": name, "size_mb": round(tflite.stat().st_size / 2 ** 20, 2),
               "params_m": round(model.count_params() / 1e6, 2),
               "photo_p50_ms": lat["photo_ms"]["p50"], "photo_p95_ms": lat["photo_ms"]["p95"],
               "case_p50_ms": lat["case_ms"]["p50"], "case_p95_ms": lat["case_ms"]["p95"],
               "auc_roc": a.get("auc_roc"), "delta_auc_roc": a.get("delta_auc_roc"),
               "delta_auc_roc_ci_low": a.get("delta_auc_roc_ci_low"),
               "delta_auc_roc_ci_high": a.get("delta_auc_roc_ci_high")}
        row["preferable"] = bool(name != REFERENCE and (row["delta_auc_roc_ci_low"] or 0) > 0
                                 and row["case_p95_ms"] <= cfg["max_p95_ms_case"])
        rows.append(row)
        print(f"{name:20s} {row['params_m']:6.2f} M  {row['size_mb']:6.2f} MB  caso p95 "
              f"{row['case_p95_ms']:7.1f} ms  AUC {row['auc_roc']}")
    run.save_metrics(rows, details={"source_run": cfg["source_run"]})
    print(f"Corrida registrada en {run.results_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
