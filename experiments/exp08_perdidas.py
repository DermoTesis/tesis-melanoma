"""EXP-08: funciones de pérdida para el desbalance: BCE, focal loss y asymmetric loss (ASL).

    python experiments/exp08_perdidas.py
    python experiments/exp08_perdidas.py --set resume=exp08/<id>    # retoma una corrida cortada

Lo pidió el asesor. EXP-03 ya probó la focal loss, pero sin el balanceo α, solo en el modelo de una
foto y con un límite de épocas que la cortó en el fold 4. Aquí se prueban la focal loss y la ASL
completas, en los dos modelos y con varias semillas.

Diseño:
- Variantes (`variants` en la config). Solo cambia la pérdida, con los hiperparámetros de los
  artículos originales, sin ajustarlos con nuestros datos:
  - `bce`: entropía cruzada binaria, la referencia;
  - `focal`: Lin et al. (2017), con γ = 2 y α = 0.25;
  - `asl`: Ridnik et al. (2021), con γ+ = 0, γ− = 4 y margen m = 0.05, como su entrenamiento
    oficial. Descarta los benignos que el modelo ya da por benignos y concentra el entrenamiento
    en los que se parecen al melanoma, que son las falsas alarmas.
- Para cada semilla (42, 142 y 242) y variante:
  1. el modelo de una foto en los 5 folds (8,512 imágenes), como EXP-03;
  2. la fusión de dos fotos en los 5 folds (1,662 lesiones), como EXP-06, desde los modelos del
     paso 1 y con la misma pérdida.
- Los pares de validación de la fusión quedan fijos en todas las semillas (los de EXP-06): solo
  cambia el azar del entrenamiento.
- Más épocas que en EXP-03 y EXP-06: una foto 5 + hasta 30 y fusión 10 + hasta 25. Son las mismas
  para todas las variantes, con parada temprana de 5 épocas.
- Orden: semilla por semilla, y dentro de cada una las tres variantes. Así, si hay que cortar,
  quedan semillas completas. Son unas 12 a 14 horas en la RTX 5060.

Criterio de decisión, fijado antes de correr. Decide la fusión, que es el modelo definitivo:
- Para cada semilla, Δ = variante − BCE de esa misma semilla, sobre las mismas lesiones. Se
  reporta la media de Δ entre semillas, con IC 95% por bootstrap de lesiones (el mismo
  remuestreo para las tres semillas).
- Una pérdida se adopta solo si se cumplen las tres condiciones:
  a. el IC del ΔAUC-ROC medio queda sobre 0;
  b. el ΔAUC-ROC es positivo en las tres semillas;
  c. el IC de la Δespecificidad media con sensibilidad 90% no queda entero bajo 0.
  Si las dos cumplen, gana la de mayor ΔAUC medio. Si ninguna cumple, se queda BCE.
- El modelo de una foto se compara igual, pero es secundario y no decide.
- Si se adopta una pérdida, hay que rehacer los pasos 1 y 2 de EXP-04 con ella. El test sigue sin
  tocarse.

También reporta la media ± desviación entre semillas de cada métrica (la variabilidad del
entrenamiento, que el bootstrap no mide) y cuántos folds llegaron al límite de épocas.

Si se corta (la PC se suspende o se apaga), se retoma con `--set resume=exp08/<id>`. Cada fold
terminado queda en `outputs/exp08/<id>/<variante>_s<semilla>/` y no se repite. Un fold a medias
se renombra a `*.interrumpido-<fecha>` y se vuelve a entrenar.
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

CONFIG = PROJECT_ROOT / "configs" / "exp08_perdidas.yaml"
REFERENCE = "bce"
STAGES = {"single_view": "una_foto", "two_view": "dos_fotos"}
DECIDES = "two_view"
# Columnas que se guardan por variante y semilla (las degradadas quedan en outputs/).
COLUMNS = {"single_view": ("prob",), "two_view": ("fusion", "single_a", "average")}
KEYS = {"single_view": ["image_id", "lesion_id", "dx", "label", "fold"],
        "two_view": ["lesion_id", "image_a", "image_b", "label", "dx", "dataset", "fold"]}
SCORE = {"single_view": "prob", "two_view": "fusion"}   # la predicción que se compara
EXPERIMENT_KEYS = ("variants", "seeds", "single_view", "two_view", "resume", "folds")


def stage_config(cfg: dict[str, Any], variant: str, seed: int, stage: str) -> dict[str, Any]:
    """Lo que ve el entrenamiento de un fold: la config base, la de la etapa y la pérdida."""
    out = deep_merge({k: v for k, v in cfg.items() if k not in EXPERIMENT_KEYS}, cfg[stage])
    out["training"] = deep_merge(out["training"], cfg["variants"][variant])
    out["seed"] = int(seed)
    return out


def unit_name(variant: str, seed: int) -> str:
    return f"{variant}_s{seed}"


def fold_dir(artifacts: Path, variant: str, seed: int, stage: str, fold: int) -> Path:
    return artifacts / unit_name(variant, seed) / STAGES[stage] / f"fold_{fold}"


def is_done(directory: Path) -> bool:
    return (directory / "predicciones.csv").is_file() and (directory / "info.json").is_file()


def main(argv: list[str] | None = None) -> int:
    cfg, _ = parse_cli(__doc__.splitlines()[0], CONFIG, argv)
    if REFERENCE not in cfg["variants"]:
        raise SystemExit(f"Falta la variante de referencia {REFERENCE!r}")
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
        run = start_run(cfg, cfg["experiment"], "perdidas")
        print(f"Corrida exp08/{run.run_id}. Si se corta: --set resume=exp08/{run.run_id}")

    plan = [(seed, variant, stage, fold) for seed in cfg["seeds"] for variant in cfg["variants"]
            for stage in STAGES for fold in cfg["folds"]]
    pending = [(seed, variant, stage, fold) for seed, variant, stage, fold in plan
               if not is_done(fold_dir(run.artifacts_dir, variant, seed, stage, fold))]
    print(f"{len(plan) - len(pending)} de {len(plan)} folds ya están hechos")
    for seed, variant, stage, fold in pending:
        _train(cfg, run.artifacts_dir, variant, seed, stage, fold, splits, images_dir)
        if fold == cfg["folds"][-1]:
            _print_unit(cfg, run.artifacts_dir, variant, seed, stage)

    analyze(cfg, run, devices)
    return 0


def _train(cfg, artifacts: Path, variant: str, seed: int, stage: str, fold: int, splits,
           images_dir: Path) -> None:
    from melanoma.multiview import two_view_fold
    from melanoma.training import run_isolated, train_fold_isolated

    out_dir = fold_dir(artifacts, variant, seed, stage, fold)
    if out_dir.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        stale = out_dir.with_name(f"{out_dir.name}.interrumpido-{stamp}")
        out_dir.rename(stale)
        print(f"Fold a medias: se guardó como {stale.name} y se vuelve a entrenar")
    print(f"\n=== Semilla {seed}, {variant}, {STAGES[stage]}, fold {fold} ===")
    stage_cfg = stage_config(cfg, variant, seed, stage)
    start = time.perf_counter()
    if stage == "single_view":
        pred, info = train_fold_isolated(stage_cfg, splits, fold, images_dir, out_dir)
    else:
        single = fold_dir(artifacts, variant, seed, "single_view", fold) / "modelo.keras"
        pred, info = run_isolated(two_view_fold, stage_cfg, splits, fold, images_dir, single, out_dir)
    info["wall_seconds"] = round(time.perf_counter() - start, 1)
    info["max_epochs"] = sum(p["epochs"] for p in stage_cfg["training"]["phases"].values())
    (out_dir / "info.json").write_text(json.dumps(info, default=_jsonable, ensure_ascii=False),
                                       encoding="utf-8")
    tmp = out_dir / "predicciones.csv.tmp"
    pred.to_csv(tmp, index=False, float_format="%.6f")
    tmp.rename(out_dir / "predicciones.csv")        # al final: marca el fold como terminado
    print(f"Fold terminado en {info['wall_seconds'] / 60:.1f} min (mejor época {info['best_epoch']} "
          f"de {info['max_epochs']})")


def _jsonable(obj: Any) -> Any:
    if hasattr(obj, "tolist"):
        return obj.tolist()
    raise TypeError(f"No se puede serializar {type(obj).__name__}")


def _print_unit(cfg, artifacts: Path, variant: str, seed: int, stage: str) -> None:
    from melanoma.metrics import point_metrics

    df = load_unit(cfg, artifacts, variant, seed, stage)
    m = point_metrics(df.label, df[SCORE[stage]], cfg["metrics"]["target_recall"])
    print(f"--> semilla {seed}, {variant}, {STAGES[stage]}: AUC-ROC fuera de fold {m['auc_roc']:.4f}")


def load_unit(cfg, artifacts: Path, variant: str, seed: int, stage: str):
    import pandas as pd

    return pd.concat([pd.read_csv(fold_dir(artifacts, variant, seed, stage, f) / "predicciones.csv")
                      for f in cfg["folds"]], ignore_index=True)


def collect(cfg, artifacts: Path, stage: str):
    """Una fila por imagen (una foto) o lesión (fusión) y una columna por variante y semilla.

    Al unir por las columnas clave (incluidos los pares A y B) se verifica que todas las variantes
    y semillas predijeron exactamente lo mismo.
    """
    wide = None
    for seed in cfg["seeds"]:
        for variant in cfg["variants"]:
            df = load_unit(cfg, artifacts, variant, seed, stage)
            df = df[KEYS[stage] + list(COLUMNS[stage])].rename(
                columns={c: column(stage, c, variant, seed) for c in COLUMNS[stage]})
            if wide is None:
                wide = df
                continue
            merged = wide.merge(df, on=KEYS[stage], validate="one_to_one")
            if len(merged) != len(wide) or len(merged) != len(df):
                raise SystemExit(f"{unit_name(variant, seed)} ({STAGES[stage]}) no predijo las mismas "
                                 "imágenes o pares que las demás")
            wide = merged
    return wide


def column(stage: str, name: str, variant: str, seed: int) -> str:
    unit = unit_name(variant, seed)
    return unit if stage == "single_view" else f"{name}_{unit}"


def verdict(comparison: dict[str, Any], op: str) -> str:
    """Las tres condiciones del criterio (ver el docstring)."""
    passes = (comparison["delta_auc_roc_ci_low"] > 0
              and all(d > 0 for d in comparison["delta_auc_roc_by_seed"])
              and comparison[f"delta_specificity_{op}_ci_high"] >= 0)
    return "cumple" if passes else "no cumple"


def analyze(cfg: dict[str, Any], run, devices: dict[str, Any]) -> None:
    from melanoma.metrics import compare_paired_seeds, point_metrics

    m = cfg["metrics"]
    target = m["target_recall"]
    op = f"s{round(target * 100)}"
    boot = (target, m["bootstrap_resamples"], m["confidence_level"], cfg["seed"])
    seeds, variants = cfg["seeds"], list(cfg["variants"])
    rows: list[dict[str, Any]] = []
    comparisons: dict[str, dict[str, Any]] = {}
    summary: dict[str, dict[str, Any]] = {}
    for stage in STAGES:
        wide = collect(cfg, run.artifacts_dir, stage)
        wide.to_csv(run.results_dir / f"predicciones_{STAGES[stage]}.csv", index=False,
                    float_format="%.6f")
        y, groups = wide.label.to_numpy(), wide.lesion_id.to_numpy()
        score = lambda variant, seed: wide[column(stage, SCORE[stage], variant, seed)]  # noqa: E731
        summary[stage] = {}
        for variant in variants:
            per_seed = []
            for seed in seeds:
                point = point_metrics(y, score(variant, seed), target)
                per_seed.append(point)
                rows.append({"stage": STAGES[stage], "variant": variant, "seed": seed, "fold": "oof",
                             "n": int(len(y)), **point})
            stats = mean_sd(per_seed, ("auc_roc", "pr_auc", f"specificity_{op}", "recall_t50"))
            summary[stage][variant] = {**stats, "auc_by_seed": [p["auc_roc"] for p in per_seed]}
            rows.append({"stage": STAGES[stage], "variant": variant, "seed": "media", "fold": "oof",
                         "n": int(len(y)), **stats})
        comparisons[stage] = {}
        for variant in variants:
            if variant == REFERENCE:
                continue
            print(f"Comparando {variant} con {REFERENCE} ({STAGES[stage]})...")
            c = compare_paired_seeds(y, [score(REFERENCE, s) for s in seeds],
                                     [score(variant, s) for s in seeds], groups, *boot)
            c["verdict"] = verdict(c, op)
            comparisons[stage][variant] = c
            rows.append({"stage": STAGES[stage], "variant": f"{variant} - {REFERENCE}",
                         "seed": "media", "fold": "oof", **c})

    passing = {v: c for v, c in comparisons[DECIDES].items() if c["verdict"] == "cumple"}
    chosen = max(passing, key=lambda v: passing[v]["delta_auc_roc"]) if passing else REFERENCE
    training = training_summary(cfg, run.artifacts_dir)
    run.save_metrics(rows, details={"devices": devices, "chosen_loss": chosen,
                                    "decides": STAGES[DECIDES], "summary": summary,
                                    "training": training})
    print_summary(cfg, summary, comparisons, op, chosen, training)
    print(f"Corrida registrada en {run.results_dir}")


def mean_sd(per_seed: list[dict[str, float]], keys) -> dict[str, float]:
    """Media y desviación estándar muestral entre semillas (0 si hay una sola)."""
    import numpy as np

    out = {}
    for key in keys:
        values = np.array([p[key] for p in per_seed], dtype=float)
        out[f"{key}_mean"] = float(values.mean())
        out[f"{key}_sd"] = float(values.std(ddof=1)) if len(values) > 1 else 0.0
    return out


def training_summary(cfg, artifacts: Path) -> dict[str, Any]:
    """Por variante, semilla y etapa: mejor época, épocas corridas y si llegó al límite."""
    out: dict[str, Any] = {}
    for seed in cfg["seeds"]:
        for variant in cfg["variants"]:
            for stage in STAGES:
                folds = {}
                for fold in cfg["folds"]:
                    info = json.loads((fold_dir(artifacts, variant, seed, stage, fold)
                                       / "info.json").read_text(encoding="utf-8"))
                    folds[str(fold)] = {
                        "best_epoch": info["best_epoch"], "max_epochs": info["max_epochs"],
                        "epochs_run": info["head_epochs"] + info["finetune_epochs"],
                        "at_limit": info["best_epoch"] >= info["max_epochs"],
                        "best_val_auc_keras": info.get("best_val_auc_keras"),
                        "train_seconds": info.get("train_seconds")}
                out[f"{unit_name(variant, seed)}/{STAGES[stage]}"] = folds
    return out


def print_summary(cfg, summary, comparisons, op, chosen, training) -> None:
    for stage in STAGES:
        role = "decide" if stage == DECIDES else "secundario"
        print(f"\n{STAGES[stage]} ({role}); AUC-ROC por semilla {cfg['seeds']}")
        print(f"{'Variante':9s} {'AUC media ± DE':18s} {'por semilla':26s} {'ΔAUC media [IC 95%]':28s} "
              f"{'ΔAUC por semilla':26s} {'ΔEspec. s90 [IC]':24s} Criterio")
        for variant, s in summary[stage].items():
            line = (f"{variant:9s} {s['auc_roc_mean']:.4f} ± {s['auc_roc_sd']:.4f}    "
                    f"{' '.join(f'{a:.4f}' for a in s['auc_by_seed']):26s} ")
            c = comparisons[stage].get(variant)
            if c:
                line += (f"{c['delta_auc_roc']:+.4f} [{c['delta_auc_roc_ci_low']:+.4f}, "
                         f"{c['delta_auc_roc_ci_high']:+.4f}]  "
                         f"{' '.join(f'{d:+.4f}' for d in c['delta_auc_roc_by_seed']):26s} "
                         f"{c[f'delta_specificity_{op}']:+.3f} [{c[f'delta_specificity_{op}_ci_low']:+.3f}, "
                         f"{c[f'delta_specificity_{op}_ci_high']:+.3f}]  {c['verdict']}")
            else:
                line += "referencia"
            print(line)
    at_limit = sum(f["at_limit"] for unit in training.values() for f in unit.values())
    total = sum(len(unit) for unit in training.values())
    print(f"\nFolds cuya mejor época fue la última permitida: {at_limit} de {total}")
    print(f"Pérdida elegida para el modelo definitivo: {chosen}"
          + ("" if chosen == REFERENCE else " (rehacer los pasos 1 y 2 de EXP-04 con ella)"))


if __name__ == "__main__":
    sys.exit(main())
