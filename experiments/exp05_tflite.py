"""EXP-05: conversión y cuantización a .tflite de los modelos de una o de dos fotos (HU16).

    python experiments/exp05_tflite.py                                        # EXP-02, una foto
    python experiments/exp05_tflite.py --config configs/exp05_tflite_dos_fotos.yaml   # EXP-06
    python experiments/exp05_tflite.py --set "folds=[0]" --set data.max_images=200   # prueba

Con el modelo de dos fotos se usan los mismos pares (A, B) de validación que en EXP-06, una fila
por lesión, y `data.max_images` limita las lesiones.

Corre en CPU (contenedor de desarrollo). Para cada fold convierte su modelo a float32, float16,
rango dinámico e int8, y predice su fold de validación con Keras y con cada `.tflite`. Con las
predicciones fuera de fold de todos los folds mide, frente a Keras:
- la diferencia de AUC-ROC, con IC por bootstrap pareado de lesiones;
- la sensibilidad en el umbral con el que Keras llega al 90% (el operativo se fija en EXP-04) y
  cuántas imágenes cambian de clase.
Además mide el `.tflite` en float32 con las fotos leídas con Pillow, como en el backend, para ver
cuánto pesa la diferencia de preprocesamiento.

Con el modelo del primer fold mide tamaño, latencia limitada a 2 núcleos (una foto, un caso de 2
fotos, 4 casos a la vez y 4 casos leyendo las JPEG) y arranque en frío. Elige el formato más liviano
que cumple todos los umbrales de `satisficing`; la decisión final se confirma en Cloud Run.
"""

from __future__ import annotations

import os
import sys
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from typing import Any

from melanoma.config import parse_cli
from melanoma.runs import PROJECT_ROOT, start_run

CONFIG = PROJECT_ROOT / "configs" / "exp05_tflite.yaml"


def main(argv: list[str] | None = None) -> int:
    cfg, _ = parse_cli(__doc__.splitlines()[0], CONFIG, argv)
    import keras
    import numpy as np
    import pandas as pd
    import tensorflow as tf
    import yaml
    from sklearn.metrics import roc_auc_score

    from melanoma.data.pipeline import limit_images, load_image
    from melanoma.data.splits import load_splits, train_val
    from melanoma.data.views import fixed_pairs, multi_image_lesions
    from melanoma.multiview import limit_lesions
    from melanoma.export_tflite import FORMATS, benchmark, cold_start, convert, load_trained
    from melanoma.metrics import at_threshold, compare_paired, threshold_for_recall
    from melanoma.serving import TFLiteClassifier, preprocess

    formats = cfg["formats"]
    if set(formats) - set(FORMATS):
        raise SystemExit(f"Formatos desconocidos {sorted(set(formats) - set(FORMATS))}")
    source_results = PROJECT_ROOT / cfg["paths"]["results"] / cfg["source_run"]
    source_models = PROJECT_ROOT / cfg["paths"]["outputs"] / cfg["source_run"]
    source_cfg = yaml.safe_load((source_results / "config.yaml").read_text())
    size = source_cfg["data"]["image_size"]
    fusion_cfg = source_cfg.get("fusion")   # solo en EXP-06: modelo de dos fotos
    splits = load_splits(PROJECT_ROOT / cfg["paths"]["splits"] / source_cfg["split"]["name"])
    images_dir = PROJECT_ROOT / cfg["data"]["sources"]["ham10000"]["images"]
    load = os.getloadavg()[0]
    if load > 1.5:
        print(f"Aviso: la CPU está ocupada (carga {load:.1f}); las latencias saldrán peores.")

    run = start_run(cfg, "exp05", "tflite-dos-fotos" if fusion_cfg else "tflite")
    print(f"Corrida {run.run_id}, modelos de {cfg['source_run']}")
    decode = tf.function(lambda path: load_image(path, size))

    def tf_images(image_ids) -> np.ndarray:
        return np.stack([decode(tf.constant(str(images_dir / f"{i}.jpg"))).numpy()
                         for i in image_ids])

    def items(arrays: list):
        """Lo que recibe el `.tflite`: fotos sueltas o pares (A, B)."""
        return list(zip(*arrays)) if len(arrays) == 2 else arrays[0]

    def keras_predict(model, arrays: list[np.ndarray]) -> np.ndarray:
        def chunk(x: np.ndarray, i: int) -> np.ndarray:
            return x[i:i + 64].astype("float32")
        if len(arrays) == 2:
            return np.concatenate([model.predict({"view_a": chunk(arrays[0], i),
                                                 "view_b": chunk(arrays[1], i)}, verbose=0).ravel()
                                   for i in range(0, len(arrays[0]), 64)])
        return np.concatenate([model.predict(chunk(arrays[0], i), verbose=0).ravel()
                               for i in range(0, len(arrays[0]), 64)])

    all_preds, tflite_paths, bench_jpegs = [], {}, None
    for fold in cfg["folds"]:
        print(f"\n=== Fold {fold} ===")
        train_df, val_df = train_val(splits, fold)
        out_dir = run.artifacts_dir / f"fold_{fold}"
        out_dir.mkdir(parents=True, exist_ok=True)
        keras.backend.clear_session()
        model = load_trained(source_models / f"fold_{fold}" / "modelo.keras", source_cfg["model"],
                             size, fusion_cfg)
        limit, seed = cfg["data"].get("max_images"), cfg["seed"] + fold
        if fusion_cfg:
            # Los mismos pares que en EXP-06 (misma semilla por fold).
            pair_seed = source_cfg["seed"] + fold
            pred = fixed_pairs(limit_lesions(multi_image_lesions(val_df), limit, pair_seed), pair_seed)
            columns = ["image_a", "image_b"]
            rep = fixed_pairs(multi_image_lesions(train_df), pair_seed)
        else:
            pred = limit_images(val_df, limit, seed)[["image_id", "lesion_id", "dx", "label"]]
            columns = ["image_id"]
            rep = train_df
        pred = pred.assign(fold=fold).reset_index(drop=True)
        arrays = [tf_images(pred[c]) for c in columns]
        jpegs = [[(images_dir / f"{i}.jpg").read_bytes() for i in pred[c]] for c in columns]
        if bench_jpegs is None:   # en pares (A, B) consecutivos con el modelo de dos fotos
            bench_jpegs = [j for group in zip(*jpegs) for j in group][:cfg["benchmark"]["images"]]
        pred["prob_keras"] = keras_predict(model, arrays)
        rep = rep.sample(n=min(cfg["representative_samples"], len(rep)), random_state=seed)
        representative = items([tf_images(rep[c]) for c in columns])
        for fmt in formats:
            blob = convert(model, fmt, representative if fmt == "int8" else None)
            path = out_dir / f"{fmt}.tflite"
            path.write_bytes(blob)
            tflite_paths.setdefault(fmt, path)
            clf = TFLiteClassifier(blob, num_threads=os.cpu_count())
            pred[f"prob_{fmt}"] = clf.predict(items(arrays))
            if fmt == "float32":
                pillow = [[preprocess(j, size) for j in group] for group in jpegs]
                pred["prob_float32_pillow"] = clf.predict(items(pillow))
            print(f"{fmt}: {len(blob) / 1e6:.1f} MB, diferencia máxima con Keras "
                  f"{np.abs(pred[f'prob_{fmt}'] - pred.prob_keras).max():.4f}")
        all_preds.append(pred)
    preds = pd.concat(all_preds, ignore_index=True)
    preds.to_csv(run.artifacts_dir / "predicciones_val.csv", index=False, float_format="%.6f")

    m, sat = cfg["metrics"], cfg["satisficing"]
    target = m["target_recall"]
    y = preds.label.to_numpy()
    threshold = threshold_for_recall(y, preds.prob_keras.to_numpy(), target)
    # A mitad de camino hasta la probabilidad siguiente: en el umbral exacto cae un melanoma, y una
    # diferencia de redondeo de 1e-7 del `.tflite` lo cambiaba de clase sin que el modelo cambiara.
    lower = preds.prob_keras[preds.prob_keras < threshold]
    threshold = float((threshold + lower.max()) / 2) if len(lower) else threshold
    keras_pos = preds.prob_keras.to_numpy() >= threshold
    keras_recall = at_threshold(y, preds.prob_keras.to_numpy(), threshold)["recall"]
    accuracy: dict[str, dict[str, Any]] = {}
    for variant in [*formats, "float32_pillow"]:
        p = preds[f"prob_{variant}"].to_numpy()
        row = compare_paired(y, preds.prob_keras, p, preds.lesion_id, target,
                             m["bootstrap_resamples"], m["confidence_level"], cfg["seed"],
                             keys=("auc_roc",))
        recall = at_threshold(y, p, threshold)["recall"]
        row.update({"auc_roc": float(roc_auc_score(y, p)), "recall_at_keras_threshold": recall,
                    "sensitivity_drop_points": (keras_recall - recall) * 100,
                    "class_changes": int(np.sum((p >= threshold) != keras_pos)),
                    "max_abs_prob_diff": float(np.abs(p - preds.prob_keras).max())})
        accuracy[variant] = row
    auc_keras = float(roc_auc_score(y, preds.prob_keras))

    bench = cfg["benchmark"]
    latency: dict[str, dict[str, Any]] = {}
    context = get_context("spawn")
    for fmt in formats:
        busy = os.getloadavg()[0]
        print(f"Midiendo latencia de {fmt} (carga de la CPU: {busy:.1f})...")
        with ProcessPoolExecutor(max_workers=1, mp_context=context) as pool:
            latency[fmt] = pool.submit(benchmark, tflite_paths[fmt], bench_jpegs, size,
                                       bench["threads"], bench["warmup_runs"], bench["timed_runs"],
                                       sat["concurrent_cases"]).result()
        latency[fmt]["cold_start"] = cold_start(tflite_paths[fmt], bench["threads"], size,
                                                bench["cold_start_runs"])
        latency[fmt]["size_mb"] = tflite_paths[fmt].stat().st_size / 1e6
        latency[fmt]["cpu_load_before"] = busy

    rows = [{"variant": "keras", "auc_roc": auc_keras, "threshold": threshold,
             "recall_at_keras_threshold": keras_recall, "n_images": len(preds)}]
    passing = []
    for variant, acc in accuracy.items():
        row: dict[str, Any] = {"variant": variant, **acc}
        checks = {"auc": -acc["delta_auc_roc"] <= sat["max_auc_drop"],
                  "sensitivity": acc["sensitivity_drop_points"] <= sat["max_sensitivity_drop_points"]}
        if variant in latency:
            lat = latency[variant]
            row.update({"size_mb": lat["size_mb"], "photo_p50_ms": lat["photo_ms"]["p50"],
                        "photo_p95_ms": lat["photo_ms"]["p95"], "case_p95_ms": lat["case_ms"]["p95"],
                        "case_concurrent_p95_ms": lat["case_concurrent_ms"]["p95"],
                        "case_full_concurrent_p95_s": lat["case_full_concurrent_ms"]["p95"] / 1000,
                        "cold_start_p95_s": lat["cold_start"]["total_s"]["p95"]})
            checks.update({
                "size": row["size_mb"] <= sat["max_size_mb"],
                "case": row["case_p95_ms"] <= sat["max_p95_ms_single_case"],
                "case_concurrent": row["case_concurrent_p95_ms"] <= sat["max_p95_ms_concurrent_cases"],
                "case_full": row["case_full_concurrent_p95_s"] <= sat["max_p95_case_s"],
                "cold_start": row["cold_start_p95_s"] <= sat["max_cold_start_s"]})
        row["fails"] = ",".join(k for k, ok in checks.items() if not ok)
        row["passes"] = not row["fails"]
        if variant in latency and row["passes"]:
            passing.append(row)
        rows.append(row)
    chosen = min(passing, key=lambda r: r["size_mb"])["variant"] if passing else None

    run.save_metrics(rows, details={"chosen_format": chosen, "keras_threshold": threshold,
                                    "latency": latency, "cpu_load_before": load,
                                    "satisficing": sat, "folds": cfg["folds"]})
    print(f"\n{'Variante':16s} {'MB':>5s} {'AUC':>7s} {'ΔAUC [IC 95%]':>28s} {'ΔSens':>6s} "
          f"{'Cambios':>7s} {'Caso p95':>9s} {'4 casos':>8s} {'Completo':>9s} {'Frío':>6s}  Cumple")
    for r in rows[1:]:
        ci = f"{r['delta_auc_roc']:+.4f} [{r['delta_auc_roc_ci_low']:+.4f}, {r['delta_auc_roc_ci_high']:+.4f}]"
        lat = (f"{r['case_p95_ms']:7.1f}ms {r['case_concurrent_p95_ms']:6.1f}ms "
               f"{r['case_full_concurrent_p95_s']:8.3f}s {r['cold_start_p95_s']:5.2f}s"
               if "size_mb" in r else f"{'':36s}")
        size_mb = f"{r['size_mb']:5.1f}" if "size_mb" in r else "     "
        print(f"{r['variant']:16s} {size_mb} {r['auc_roc']:7.4f} {ci:>28s} "
              f"{r['sensitivity_drop_points']:+6.2f} {r['class_changes']:7d} {lat}  "
              f"{'sí' if r['passes'] else 'no (' + r['fails'] + ')'}")
    print(f"Keras: AUC {auc_keras:.4f}; umbral con sensibilidad {target:.0%}: {threshold:.4f}")
    print(f"Formato elegido (filtro local; se confirma en Cloud Run): {chosen}")
    print(f"Corrida registrada en {run.results_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
