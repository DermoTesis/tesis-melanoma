"""EXP-04, pasos 2 y 3: calibración, umbral con margen y la única evaluación del test (CPU).

    python experiments/exp04_evaluacion.py --set final_run=exp04/<id del paso 1>
    python experiments/exp04_evaluacion.py --set final_run=exp04/<id del paso 1> \\
        --set evaluate_test=true --set preregistered_run=exp04/<id del paso 2>

Paso 2, registro previo. Con el mismo camino que el servidor (fotos leídas con Pillow y modelos
.tflite en `format`):
- predice fuera de fold las lesiones de validación con 2 o más fotos, con los pares de EXP-06:
  la fusión, una foto (A) y el promedio de las dos;
- elige la calibración por ECE fuera de fold;
- fija, para cada uno de esos tres, el umbral con el que la sensibilidad es >= 90% con 95% de
  confianza (ver `melanoma.calibration`);
- convierte los modelos finales del paso 1 y guarda el artefacto versionado del servidor: el
  `.tflite`, la calibración y el umbral (RNF-13, HU19).
Todo queda en `registro.json`, que hay que commitear (y subir) ANTES del paso 3. Limitación: el
umbral y la calibración salen de los modelos de los folds y se aplican al modelo final, entrenado
con más datos; el margen del umbral también cubre parte de esa diferencia.

Paso 3, una sola vez. Con lo registrado, sin recalcular nada:
- población principal: las lesiones del test con 2 o más fotos, con un par fijo (A, B), porque la
  app siempre toma dos fotos;
- población secundaria: todas las lesiones del test; las de una foto, con la foto repetida (el
  respaldo de una foto de HU36).
Hipótesis registradas (umbrales fijos; IC 95% por bootstrap de lesiones):
- H1: sensibilidad de la fusión >= 90% en la población principal. "Se cumple" si la estimación
  llega; "con 95% de confianza" si también llega el límite inferior del IC.
- H2: la fusión tiene mayor AUC-ROC que una foto (A): IC del Δ sobre 0.
- H3: con la foto A degradada (las 5 degradaciones de EXP-06) y los umbrales fijos, la fusión
  detecta más melanomas que el promedio: el promedio de las 5 diferencias de sensibilidad tiene
  IC sobre 0. Confirma el hallazgo exploratorio de EXP-06.
El script se niega a evaluar el test si ya hay una evaluación en `resultados/exp04/` o si el
registro no está commiteado.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from melanoma.config import parse_cli
from melanoma.runs import PROJECT_ROOT, start_run

CONFIG = PROJECT_ROOT / "configs" / "exp04_calibracion.yaml"
METHODS = {"single_a": "Una foto", "average": "Promedio de las dos", "fusion": "Fusión aprendida"}
REGISTRY = "registro.json"
TEST_FILE = "evaluacion_test.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    cfg, _ = parse_cli(__doc__.splitlines()[0], CONFIG, argv)
    if not cfg.get("final_run"):
        raise SystemExit("Falta --set final_run=exp04/<id del paso 1>")
    if cfg["evaluate_test"]:
        return evaluate_test(cfg)
    return register(cfg)


def _context(cfg: dict[str, Any]) -> dict[str, Any]:
    import yaml

    from melanoma.data.splits import load_splits

    results, outputs = PROJECT_ROOT / cfg["paths"]["results"], PROJECT_ROOT / cfg["paths"]["outputs"]
    two_cfg = yaml.safe_load((results / cfg["two_view_run"] / "config.yaml").read_text())
    return {"results": results, "outputs": outputs, "two_cfg": two_cfg,
            "size": cfg["data"]["image_size"],
            "splits": load_splits(PROJECT_ROOT / cfg["paths"]["splits"] / cfg["split"]["name"]),
            "images_dir": PROJECT_ROOT / cfg["data"]["sources"]["ham10000"]["images"]}


def _pillow(image_ids, ctx) -> "np.ndarray":  # noqa: F821
    import numpy as np

    from melanoma.serving import preprocess

    return np.stack([preprocess((ctx["images_dir"] / f"{i}.jpg").read_bytes(), ctx["size"])
                     for i in image_ids])


def _to_tflite(keras_path: Path, out_path: Path, cfg, ctx, fusion_cfg=None) -> Path:
    import keras

    from melanoma.export_tflite import convert, load_trained

    keras.backend.clear_session()
    model = load_trained(keras_path, cfg["model"], ctx["size"], fusion_cfg)
    out_path.write_bytes(convert(model, cfg["format"]))
    return out_path


def register(cfg: dict[str, Any]) -> int:
    """Paso 2: predicciones fuera de fold, calibración, umbrales y artefacto final."""
    import numpy as np
    import pandas as pd

    from melanoma import calibration
    from melanoma.metrics import evaluate_at
    from melanoma.serving import TFLiteClassifier

    ctx = _context(cfg)
    m = cfg["metrics"]
    run = start_run(cfg, "exp04", "registro")
    print(f"Corrida {run.run_id}: registro previo a la evaluación del test")
    oof = pd.read_csv(ctx["results"] / cfg["two_view_run"] / "predicciones_val.csv")
    oof = oof[["lesion_id", "image_a", "image_b", "label", "dx", "dataset", "fold"]].copy()
    threads = os.cpu_count()
    for fold in sorted(oof.fold.unique()):
        rows = oof.fold == fold
        a, b = _pillow(oof.image_a[rows], ctx), _pillow(oof.image_b[rows], ctx)
        fusion = TFLiteClassifier(ctx["outputs"] / cfg["tflite_run"] / f"fold_{fold}"
                                  / f"{cfg['format']}.tflite", threads)
        single_path = _to_tflite(ctx["outputs"] / cfg["single_view_run"] / f"fold_{fold}" / "modelo.keras",
                                 run.artifacts_dir / f"una_foto_fold_{fold}.tflite", cfg, ctx)
        single = TFLiteClassifier(single_path, threads)
        oof.loc[rows, "fusion"] = fusion.predict(list(zip(a, b)))
        oof.loc[rows, "single_a"] = single.predict(a)
        oof.loc[rows, "single_b"] = single.predict(b)
        print(f"Fold {fold}: {int(rows.sum())} lesiones")
    oof["average"] = (oof.single_a + oof.single_b) / 2
    oof.to_csv(run.results_dir / "predicciones_val.csv", index=False, float_format="%.6f")

    y, groups = oof.label.to_numpy(), oof.lesion_id.to_numpy()
    boot = (m["bootstrap_resamples"], m["confidence_level"], cfg["seed"])
    thresholds = {method: calibration.threshold_with_margin(
        y, oof[method], groups, m["target_recall"], cfg["threshold_confidence"], *boot[::2])
        for method in METHODS}
    cal = calibration.choose(y, oof.fusion, oof.fold, cfg["calibration"]["methods"],
                             cfg["calibration"]["ece_bins"])
    validation = {method: evaluate_at(y, oof[method], groups, thresholds[method]["threshold"], *boot)
                  for method in METHODS}

    final_out = ctx["outputs"] / cfg["final_run"]
    fmt = cfg["format"]
    two_path = _to_tflite(final_out / "dos_fotos.keras", run.artifacts_dir / f"modelo_dos_fotos_{fmt}.tflite",
                          cfg, ctx, ctx["two_cfg"]["fusion"])
    one_path = _to_tflite(final_out / "una_foto.keras", run.artifacts_dir / f"modelo_una_foto_{fmt}.tflite",
                          cfg, ctx)
    t = thresholds["fusion"]["threshold"]
    artifact = {
        "version": run.run_id, "format": fmt, "image_size": ctx["size"],
        "model_file": two_path.name, "sha256": sha256(two_path),
        "size_mb": round(two_path.stat().st_size / 1e6, 2), "inputs": ["view_a", "view_b"],
        "single_view_fallback": "la misma foto en las dos entradas",
        "threshold": t, "calibration": cal["params"],
        "calibrated_threshold": float(calibration.apply(cal["params"], [t])[0]),
        "decision": "melanoma si la salida del modelo (sin calibrar) es >= threshold; la "
                    "probabilidad calibrada es la que se muestra al médico",
    }
    (run.artifacts_dir / "artefacto.json").write_text(json.dumps(artifact, indent=2) + "\n")
    registry = {
        "final_run": cfg["final_run"], "pairs_seed": cfg["seed"],
        "degradations": ctx["two_cfg"]["evaluation_degradations"],
        "thresholds": thresholds, "calibration": cal, "artifact": artifact,
        "comparison_models": {"single_view": {"file": one_path.name, "sha256": sha256(one_path)}},
        "validation_at_thresholds": validation,
        "hypotheses": __doc__[__doc__.index("Hipótesis registradas"):__doc__.index("El script se niega")].strip(),
    }
    (run.results_dir / REGISTRY).write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n")
    rows = [{"variant": method, "fold": "oof", "threshold_no_margin": thresholds[method]["threshold_no_margin"],
             **validation[method]} for method in METHODS]
    run.save_metrics(rows, details={"calibration": cal, "thresholds": thresholds})

    print(f"\nCalibración elegida: {cal['chosen']} (ECE fuera de fold: "
          + ", ".join(f"{k} {v['ece']:.3f}" for k, v in cal["scores"].items()) + ")")
    print(f"{'Método':20s} {'Umbral (sin margen)':22s} {'Sensibilidad [IC]':24s} Especificidad")
    for method, name in METHODS.items():
        v, th = validation[method], thresholds[method]
        print(f"{name:20s} {th['threshold']:.4f} ({th['threshold_no_margin']:.4f})    "
              f"{v['recall']:.3f} [{v['recall_ci_low']:.3f}, {v['recall_ci_high']:.3f}]   "
              f"{v['specificity']:.3f}")
    print(f"\nArtefacto: {two_path} ({artifact['size_mb']} MB), umbral {t:.4f} "
          f"(probabilidad calibrada {artifact['calibrated_threshold']:.3f})")
    print(f"Registro en {run.results_dir / REGISTRY}. Commitéalo y súbelo antes del paso 3:")
    print(f"  --set evaluate_test=true --set preregistered_run=exp04/{run.run_id}")
    return 0


def _check_preregistration(cfg: dict[str, Any], results: Path) -> Path:
    done = sorted(results.glob(f"exp04/*/{TEST_FILE}"))
    if done:
        raise SystemExit(f"El test ya se evaluó ({done[0].parent.name}); no se vuelve a evaluar.")
    if not cfg.get("preregistered_run"):
        raise SystemExit("Falta --set preregistered_run=exp04/<id del paso 2>")
    registry = results / cfg["preregistered_run"] / REGISTRY
    try:
        rel = registry.relative_to(PROJECT_ROOT)
    except ValueError:   # resultados fuera del repo: es una prueba, no la evaluación oficial
        print("Aviso: resultados fuera del repo (prueba); no se verifica el commit del registro.")
        return registry
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(rel)], cwd=PROJECT_ROOT,
                             capture_output=True).returncode == 0
    clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", str(rel)],
                           cwd=PROJECT_ROOT).returncode == 0
    if not (tracked and clean):
        raise SystemExit(f"{rel} no está commiteado tal cual: commitéalo antes de evaluar el test.")
    return registry


def evaluate_test(cfg: dict[str, Any]) -> int:
    """Paso 3: la única evaluación del test, con los umbrales y modelos registrados."""
    import numpy as np
    import pandas as pd

    from melanoma import calibration
    from melanoma.data.splits import TEST
    from melanoma.data.views import fixed_pairs
    from melanoma.figures import confusion_table, plot_matrices
    from melanoma.metrics import at_threshold, bootstrap_indices, compare_paired, evaluate_at
    from melanoma.multiview import degraded_copy
    from melanoma.serving import TFLiteClassifier

    ctx = _context(cfg)
    registry_path = _check_preregistration(cfg, ctx["results"])
    registry = json.loads(registry_path.read_text())
    if registry["final_run"] != cfg["final_run"]:
        raise SystemExit("final_run no coincide con el del registro")
    models_dir = ctx["outputs"] / cfg["preregistered_run"]
    two_path = models_dir / registry["artifact"]["model_file"]
    one_path = models_dir / registry["comparison_models"]["single_view"]["file"]
    for path, expected in ((two_path, registry["artifact"]["sha256"]),
                           (one_path, registry["comparison_models"]["single_view"]["sha256"])):
        if sha256(path) != expected:
            raise SystemExit(f"{path.name} no es el registrado (sha256 distinto)")
    thresholds = {k: v["threshold"] for k, v in registry["thresholds"].items()}
    m = cfg["metrics"]
    boot = (m["bootstrap_resamples"], m["confidence_level"], cfg["seed"])
    run = start_run(cfg, "exp04", "evaluacion-test")
    print(f"Corrida {run.run_id}: evaluación ÚNICA del test, con {cfg['preregistered_run']}")

    test = ctx["splits"][ctx["splits"].split == TEST]
    pairs = fixed_pairs(test, registry["pairs_seed"])
    a, b = _pillow(pairs.image_a, ctx), _pillow(pairs.image_b, ctx)
    two, one = TFLiteClassifier(two_path, os.cpu_count()), TFLiteClassifier(one_path, os.cpu_count())
    pred = pairs.copy()
    pred["fusion"] = two.predict(list(zip(a, b)))
    pred["single_a"], pred["single_b"] = one.predict(a), one.predict(b)
    pred["average"] = (pred.single_a + pred.single_b) / 2
    names = []
    for kind, levels in registry["degradations"].items():
        for level in levels:
            name = f"{kind}_{level:g}"
            names.append(name)
            bad = degraded_copy(a, kind, float(level))
            pred[f"fusion_{name}"] = two.predict(list(zip(bad, b)))
            pred[f"single_a_{name}"] = one.predict(bad)
            pred[f"average_{name}"] = (pred[f"single_a_{name}"] + pred.single_b) / 2
    pred["calibrated"] = calibration.apply(registry["calibration"]["params"], pred.fusion)

    singles = test[~test.lesion_id.isin(pairs.lesion_id)].drop_duplicates("lesion_id")
    only = _pillow(singles.image_id, ctx)
    secondary = pd.concat([pred[["lesion_id", "label", "dx", "fusion"]],
                           singles[["lesion_id", "label", "dx"]].assign(
                               fusion=two.predict([(x, x) for x in only]))], ignore_index=True)

    y, groups = pred.label.to_numpy(), pred.lesion_id.to_numpy()
    primary = {k: evaluate_at(y, pred[k], groups, thresholds[k], *boot) for k in METHODS}
    second = evaluate_at(secondary.label, secondary.fusion, secondary.lesion_id, thresholds["fusion"], *boot)
    h2 = compare_paired(y, pred.single_a, pred.fusion, groups, m["target_recall"], *boot)

    def robustness_delta(idx: np.ndarray) -> list[float]:
        return [at_threshold(y[idx], pred[f"fusion_{n}"].to_numpy()[idx], thresholds["fusion"])["recall"]
                - at_threshold(y[idx], pred[f"average_{n}"].to_numpy()[idx], thresholds["average"])["recall"]
                for n in names]

    point = robustness_delta(np.arange(len(y)))
    samples = np.array([robustness_delta(i) for i in bootstrap_indices(groups, boot[0], boot[2])])
    alpha = (1 - boot[1]) / 2
    h3 = {"mean_delta_recall": float(np.mean(point)),
          "ci_low": float(np.quantile(samples.mean(axis=1), alpha)),
          "ci_high": float(np.quantile(samples.mean(axis=1), 1 - alpha)),
          "by_degradation": {n: {"delta_recall": point[j],
                                 "ci_low": float(np.quantile(samples[:, j], alpha)),
                                 "ci_high": float(np.quantile(samples[:, j], 1 - alpha)),
                                 **{k: at_threshold(y, pred[f"{k}_{n}"], thresholds[k])["recall"]
                                    for k in METHODS}}
                             for j, n in enumerate(names)}}
    f = primary["fusion"]
    verdicts = {
        "H1": ("se cumple con 95% de confianza" if f["recall_ci_low"] >= m["target_recall"] else
               "se cumple" if f["recall"] >= m["target_recall"] else "no se cumple"),
        "H2": "se cumple" if h2["delta_auc_roc_ci_low"] > 0 else "no se demuestra",
        "H3": "se confirma" if h3["ci_low"] > 0 else "no se confirma",
    }
    out = {"preregistered_run": cfg["preregistered_run"], "verdicts": verdicts,
           "primary": primary, "secondary_all_lesions": second, "H2": h2, "H3": h3,
           "n_primary": {"lesions": int(len(pred)), "melanoma": int(y.sum())},
           "n_secondary": {"lesions": int(len(secondary)), "melanoma": int(secondary.label.sum())}}
    pred.to_csv(run.results_dir / "predicciones_test.csv", index=False, float_format="%.6f")
    secondary.to_csv(run.results_dir / "predicciones_test_todas.csv", index=False, float_format="%.6f")
    rows = [{"variant": k, "population": "principal", **v} for k, v in primary.items()]
    rows.append({"variant": "fusion", "population": "todas", **second})
    run.save_metrics(rows, details={"verdicts": verdicts, "H2": h2, "H3": h3})
    (run.results_dir / TEST_FILE).write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")

    labels = ["Melanoma", "No melanoma"]
    source = f"test · {len(pred)} lesiones con 2 o más fotos"
    plot_matrices([(name, confusion_table(y, pred[k], thresholds[k])) for k, name in METHODS.items()],
                  labels, run.results_dir / "matriz_confusion_test.png",
                  title=f"Matriz de confusión con el umbral registrado ({source})")
    plot_matrices([("Fusión aprendida", confusion_table(secondary.label, secondary.fusion, thresholds["fusion"]))],
                  labels, run.results_dir / "matriz_confusion_test_todas.png",
                  title=f"Todas las lesiones del test ({len(secondary)}; las de una foto, repetida)")
    for n in ("blur_8", "dark_0.25"):
        if n in names:
            plot_matrices([(name, confusion_table(y, pred[f"{k}_{n}"], thresholds[k]))
                           for k, name in METHODS.items()], labels,
                          run.results_dir / f"matriz_confusion_test_{n}.png",
                          title=f"Foto A degradada ({n}) con los umbrales registrados ({source})")

    print(f"\nPoblación principal: {len(pred)} lesiones con 2 o más fotos, {int(y.sum())} melanomas")
    for k, name in METHODS.items():
        v = primary[k]
        print(f"  {name:20s} sens {v['recall']:.3f} [{v['recall_ci_low']:.3f}, {v['recall_ci_high']:.3f}]"
              f"  esp {v['specificity']:.3f} [{v['specificity_ci_low']:.3f}, {v['specificity_ci_high']:.3f}]"
              f"  VPP {v['precision']:.3f}  VPN {v['npv']:.3f}  AUC {v['auc_roc']:.4f}"
              f" [{v['auc_roc_ci_low']:.4f}, {v['auc_roc_ci_high']:.4f}]")
    print(f"Todas las lesiones ({len(secondary)}, {int(secondary.label.sum())} melanomas): fusión sens "
          f"{second['recall']:.3f} [{second['recall_ci_low']:.3f}, {second['recall_ci_high']:.3f}], esp "
          f"{second['specificity']:.3f}, AUC {second['auc_roc']:.4f}")
    print(f"H1: {verdicts['H1']} | H2: ΔAUC {h2['delta_auc_roc']:+.4f} [{h2['delta_auc_roc_ci_low']:+.4f}, "
          f"{h2['delta_auc_roc_ci_high']:+.4f}] → {verdicts['H2']} | H3: Δsens media "
          f"{h3['mean_delta_recall']:+.3f} [{h3['ci_low']:+.3f}, {h3['ci_high']:+.3f}] → {verdicts['H3']}")
    print(f"Corrida registrada en {run.results_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
