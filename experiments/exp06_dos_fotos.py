"""EXP-06: una foto frente a dos fotos de la misma lesión, en los 5 folds (HU36, HU37).

    python experiments/exp06_dos_fotos.py
    python experiments/exp06_dos_fotos.py --set "folds=[0]" --set pairs.max_lesions=60   # prueba

Usa solo las lesiones con 2 o más fotos, con la partición por lesión de EXP-01: cada lesión de
validación tiene un par fijo de fotos (A, B). Parte de los modelos de una foto de EXP-03 (sin
balanceo) y compara, sobre las mismas lesiones y con IC por bootstrap pareado:
- una foto (A), el promedio de las dos predicciones (fusión fija, como Hekler et al. 2024) y la
  fusión aprendida (el modelo de dos fotos);
- lo mismo con la foto A degradada (desenfoque o poca luz) y la B intacta.

Criterio de decisión, fijado antes de correr (ΔAUC y Δespecificidad con sensibilidad 90%, con IC
95% pareado; la sensibilidad queda fija en 90% por requisito, así que la ganancia se ve en la
especificidad):
- H2 (dos fotos > una): ΔAUC de fusión − una foto con IC sobre 0, y la Δespecificidad no queda
  entera bajo 0. También se reporta frente a la misma red con la foto A repetida.
- H2b (fusión aprendida ≥ promedio): "la supera" si el IC de ΔAUC queda sobre 0; "la iguala" si
  queda sobre −0.01 (no inferioridad con margen 0.01); si no, no se demuestra.
- H3 (robustez a una foto mala): para cada degradación, fusión − una foto degradada y fusión −
  promedio (H3b), ambas con IC; se reportan además las caídas de AUC frente a las fotos limpias.
- Modelo definitivo para EXP-04: el de dos fotos si se cumple H2; si no, el de una foto.

Con `--config configs/exp07_datos_paciente.yaml` corre EXP-07: la misma fusión con la edad, el
sexo y la zona del cuerpo, comparada (pareada) con la fusión de la corrida `compare_run`. Criterio,
fijado antes de correr: se adoptan los datos del paciente si el IC del ΔAUC queda sobre 0 y la
Δespecificidad con sensibilidad 90% no queda entera bajo 0.
"""

from __future__ import annotations

import sys
from typing import Any

from melanoma.config import parse_cli
from melanoma.runs import PROJECT_ROOT, start_run

CONFIG = PROJECT_ROOT / "configs" / "exp06_dos_fotos.yaml"
CLEAN = ("single_a", "single_b", "average", "fusion", "fusion_single")
COMPARISONS = (("H2", "fusion", "single_a"), ("H2 misma red", "fusion", "fusion_single"),
               ("H2b", "fusion", "average"))
NON_INFERIORITY = 0.01


def main(argv: list[str] | None = None) -> int:
    cfg, _ = parse_cli(__doc__.splitlines()[0], CONFIG, argv)
    import numpy as np
    import pandas as pd
    import yaml

    from melanoma.data import ham10000
    from melanoma.data.splits import load_splits
    from melanoma.metrics import compare_paired, cv_summary, evaluate, point_metrics
    from melanoma.multiview import degradations, two_view_fold
    from melanoma.training import run_isolated, setup_devices

    single_results = PROJECT_ROOT / cfg["paths"]["results"] / cfg["single_view_run"]
    single_models = PROJECT_ROOT / cfg["paths"]["outputs"] / cfg["single_view_run"]
    single_cfg = yaml.safe_load((single_results / "config.yaml").read_text())
    for key in ("model", "split"):
        if single_cfg[key] != cfg[key]:
            raise SystemExit(f"{key} no coincide con el de {cfg['single_view_run']}")
    if single_cfg["data"]["image_size"] != cfg["data"]["image_size"]:
        raise SystemExit("data.image_size no coincide con el de los modelos de una foto")

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
    use_metadata = bool((cfg.get("metadata") or {}).get("use"))
    run = start_run(cfg, cfg["experiment"], "datos-paciente" if use_metadata else "dos-fotos")
    print(f"Corrida {run.run_id}, modelos de una foto de {cfg['single_view_run']}")
    rows, predictions, training_info = [], [], {}
    for fold in cfg["folds"]:
        print(f"\n=== Fold {fold} ===")
        pred, info = run_isolated(two_view_fold, cfg, splits, fold, images_dir,
                                  single_models / f"fold_{fold}" / "modelo.keras",
                                  run.artifacts_dir / f"fold_{fold}")
        predictions.append(pred)
        training_info[str(fold)] = info
        for variant in CLEAN:
            rows.append({"variant": variant, "fold": fold, "n_lesions": len(pred),
                         **point_metrics(pred.label, pred[variant], target)})
        print(f"Fold {fold}: AUC una foto {rows[-5]['auc_roc']:.4f}, promedio "
              f"{rows[-3]['auc_roc']:.4f}, fusión {rows[-2]['auc_roc']:.4f} "
              f"({len(pred)} lesiones, {int(pred.label.sum())} melanomas)")

    oof = pd.concat(predictions, ignore_index=True)
    oof.to_csv(run.results_dir / "predicciones_val.csv", index=False, float_format="%.6f")
    y, groups = oof.label.to_numpy(), oof.lesion_id.to_numpy()
    boot = (target, m["bootstrap_resamples"], m["confidence_level"], cfg["seed"])
    cv = {v: cv_summary([r for r in rows if r["variant"] == v]) for v in CLEAN}
    pooled = {}
    for variant in CLEAN:
        pooled[variant] = evaluate(y, oof[variant], groups, *boot)
        rows.append({"variant": variant, "fold": "oof", **pooled[variant]})
    tests = []
    for name, candidate, reference in COMPARISONS:
        tests.append({"test": name, "candidate": candidate, "reference": reference,
                      **compare_paired(y, oof[reference], oof[candidate], groups, *boot)})
    robustness = []
    for name, _, _ in degradations(cfg):
        point = {v: point_metrics(y, oof[f"{v}_{name}"], target)["auc_roc"]
                 for v in ("single_a", "average", "fusion")}
        robustness.append({"degradation": name, "auc_single_a": point["single_a"],
                           "auc_average": point["average"], "auc_fusion": point["fusion"],
                           "drop_single_a": point["single_a"] - pooled["single_a"]["auc_roc"],
                           "drop_average": point["average"] - pooled["average"]["auc_roc"],
                           "drop_fusion": point["fusion"] - pooled["fusion"]["auc_roc"],
                           "weight_a_clean": float(oof.weight_a.mean()),
                           "weight_a_degraded": float(oof[f"weight_a_{name}"].mean())})
        for label, reference in (("H3", "single_a"), ("H3b", "average")):
            tests.append({"test": label, "degradation": name, "candidate": f"fusion_{name}",
                          "reference": f"{reference}_{name}",
                          **compare_paired(y, oof[f"{reference}_{name}"], oof[f"fusion_{name}"],
                                           groups, *boot)})
    for t in tests:
        t["verdict"] = _verdict(t, op)
        rows.append({"variant": f"{t['candidate']} - {t['reference']}", "fold": "oof", **t})
    for r in robustness:
        rows.append({"variant": f"degradación {r['degradation']}", "fold": "oof", **r})

    h2 = next(t for t in tests if t["test"] == "H2")
    chosen = "dos fotos" if h2["verdict"] == "se cumple" else "una foto"
    if cfg.get("compare_run"):
        previous = pd.read_csv(PROJECT_ROOT / cfg["paths"]["results"] / cfg["compare_run"]
                               / "predicciones_val.csv")[["lesion_id", "fusion"]]
        merged = oof.merge(previous, on="lesion_id", suffixes=("", "_previous"), validate="one_to_one")
        if len(merged) != len(oof):
            raise SystemExit(f"{cfg['compare_run']} no tiene las mismas lesiones")
        comparison = compare_paired(merged.label, merged.fusion_previous, merged.fusion,
                                    merged.lesion_id, *boot)
        low, spec_high = comparison["delta_auc_roc_ci_low"], comparison[f"delta_specificity_{op}_ci_high"]
        comparison["verdict"] = "se adoptan" if low > 0 and spec_high >= 0 else "no se adoptan"
        by_source = {source: {"n": int(len(g)), "melanoma": int(g.label.sum()),
                              "auc_previous": point_metrics(g.label, g.fusion_previous, target)["auc_roc"],
                              "auc": point_metrics(g.label, g.fusion, target)["auc_roc"]}
                     for source, g in merged.groupby("dataset") if 0 < g.label.sum() < len(g)}
        rows.append({"variant": f"fusion - fusion de {cfg['compare_run']}", "fold": "oof",
                     "test": "datos del paciente", **comparison})
        chosen = "dos fotos + datos del paciente" if comparison["verdict"] == "se adoptan" else chosen
    run.save_metrics(rows, details={"cv": cv, "devices": devices, "training": training_info,
                                    "chosen_model": chosen,
                                    "n_lesions": int(len(oof)), "n_melanoma": int(y.sum())})
    _print_summary(pooled, tests, robustness, op, len(oof), int(y.sum()), chosen)
    if cfg.get("compare_run"):
        print(f"\nDatos del paciente: fusión con datos − fusión de {cfg['compare_run']}: ΔAUC "
              f"{comparison['delta_auc_roc']:+.4f} [{low:+.4f}, {comparison['delta_auc_roc_ci_high']:+.4f}]"
              f", Δespecificidad con sensibilidad {target:.0%} {comparison[f'delta_specificity_{op}']:+.3f} "
              f"[{comparison[f'delta_specificity_{op}_ci_low']:+.3f}, {spec_high:+.3f}] → {comparison['verdict']}")
        for source, v in by_source.items():
            print(f"  {source:14s} {v['n']:5d} lesiones, {v['melanoma']:3d} melanomas: AUC "
                  f"{v['auc_previous']:.4f} → {v['auc']:.4f}")
    print(f"Corrida registrada en {run.results_dir}")
    return 0


def _verdict(t: dict[str, Any], op: str) -> str:
    low, high = t["delta_auc_roc_ci_low"], t["delta_auc_roc_ci_high"]
    spec_high = t[f"delta_specificity_{op}_ci_high"]
    if t["test"] == "H2b":
        return "la supera" if low > 0 else ("la iguala" if low > -NON_INFERIORITY else "no se demuestra")
    if t["test"].startswith("H2"):
        return "se cumple" if low > 0 and spec_high >= 0 else "no se demuestra"
    return "más robusta" if low > 0 else ("no se demuestra" if high > 0 else "menos robusta")


def _print_summary(pooled, tests, robustness, op, n, n_mel, chosen) -> None:
    print(f"\n{n} lesiones con 2 o más fotos, {n_mel} con melanoma (predicciones fuera de fold)")
    print(f"{'Variante':16s} {'AUC [IC 95%]':26s} Espec. con sens. 90%")
    for variant, p in pooled.items():
        print(f"{variant:16s} {p['auc_roc']:.4f} [{p['auc_roc_ci_low']:.4f}, {p['auc_roc_ci_high']:.4f}]  "
              f"{p[f'specificity_{op}']:.3f}")
    print(f"\n{'Prueba':14s} {'Comparación':42s} {'ΔAUC [IC 95%]':28s} {'ΔEspec.':8s} Veredicto")
    for t in tests:
        name = t["test"] + (f" {t['degradation']}" if "degradation" in t else "")
        print(f"{name:14s} {t['candidate'] + ' − ' + t['reference']:42s} "
              f"{t['delta_auc_roc']:+.4f} [{t['delta_auc_roc_ci_low']:+.4f}, {t['delta_auc_roc_ci_high']:+.4f}] "
              f"{t[f'delta_specificity_{op}']:+.3f}   {t['verdict']}")
    print(f"\n{'Degradación':12s} {'Caída AUC: una foto':>20s} {'promedio':>9s} {'fusión':>8s} "
          f"{'Peso foto A (limpia → mala)':>28s}")
    for r in robustness:
        print(f"{r['degradation']:12s} {r['drop_single_a']:+20.4f} {r['drop_average']:+9.4f} "
              f"{r['drop_fusion']:+8.4f} {r['weight_a_clean']:13.2f} → {r['weight_a_degraded']:.2f}")
    print(f"\nModelo definitivo para EXP-04: {chosen}")


if __name__ == "__main__":
    sys.exit(main())
