"""Exportación a `.tflite` (EXP-05): float32, float16, rango dinámico e int8, con medición de tamaño,
latencia en CPU con 2 hilos, arranque en frío y pérdida de AUC frente a Keras.

La latencia se mide en un proceso aparte limitado a `threads` núcleos, para acercarse a las 2 vCPU
de Cloud Run sin que la medición compita con el resto del experimento. Lo medido en la PC es solo
un filtro previo: los umbrales se verifican en Cloud Run.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from melanoma.serving import TFLiteClassifier, preprocess

FORMATS = ("float32", "float16", "dynamic_range", "int8")


def load_trained(model_path: str | Path, model_cfg: dict[str, Any], image_size: int,
                 fusion_cfg: dict[str, Any] | None = None):
    """Reconstruye el modelo en float32 y le carga los pesos entrenados (de una o de dos fotos).

    El `.keras` de la GPU se guardó con precisión mixta; en CPU y en el `.tflite` eso solo
    agregaría conversiones a float16. Los pesos se guardan en float32 de todas formas. Con
    `fusion_cfg` arma el modelo de dos fotos de EXP-06.
    """
    import keras

    from melanoma.models import build_single_view, build_two_view

    keras.mixed_precision.set_global_policy("float32")
    model = build_single_view(model_cfg, image_size, weights=None)
    if fusion_cfg is not None:
        model = build_two_view(model, fusion_cfg)
    model.load_weights(model_path)
    return model


def convert(model, fmt: str,
            representative: Iterable[np.ndarray | tuple[np.ndarray, ...]] | None = None) -> bytes:
    """`.tflite` en el formato pedido. int8 cuantiza pesos y activaciones con las imágenes de
    `representative` (de entrenamiento; pares (A, B) con el modelo de dos fotos), con entrada y
    salida en float."""
    import tensorflow as tf

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    if fmt == "float16":
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        converter.target_spec.supported_types = [tf.float16]
    elif fmt == "dynamic_range":
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
    elif fmt == "int8":
        if representative is None:
            raise ValueError("int8 necesita imágenes representativas")
        samples = [tuple(np.asarray(v, dtype=np.float32)[None]
                         for v in (x if isinstance(x, tuple) else (x,))) for x in representative]
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        converter.representative_dataset = lambda: (list(x) for x in samples)
    elif fmt != "float32":
        raise ValueError(f"Formato desconocido {fmt!r}; opciones: {FORMATS}")
    return converter.convert()


def percentiles(values: Iterable[float]) -> dict[str, float]:
    values = np.asarray(list(values), dtype=float)
    return {"p50": float(np.percentile(values, 50)), "p95": float(np.percentile(values, 95))}


def limit_cpus(n: int) -> list[int]:
    """Restringe el proceso actual a sus primeros `n` núcleos (Linux)."""
    cpus = sorted(os.sched_getaffinity(0))[:n]
    os.sched_setaffinity(0, cpus)
    return cpus


def benchmark(model_path: str | Path, jpegs: list[bytes], image_size: int, threads: int,
              warmup: int, runs: int, concurrent: int) -> dict[str, Any]:
    """Latencias en ms (p50 y p95), limitado a `threads` núcleos. Pensado para un proceso aparte.

    - foto: una inferencia (con el modelo de dos fotos, una inferencia ya procesa las dos);
    - caso: las 2 fotos de un caso, un caso a la vez;
    - caso_concurrente: `concurrent` casos a la vez, cada uno con su intérprete (como las
      peticiones simultáneas de una instancia de Cloud Run);
    - caso_completo_concurrente: lo mismo, pero leyendo y redimensionando las 2 JPEG.
    """
    cpus = limit_cpus(threads)
    images = [preprocess(j, image_size) for j in jpegs]
    clf = TFLiteClassifier(model_path, threads)
    one = [images[0]] * clf.n_inputs
    for i in range(warmup):
        clf.predict_one(*[images[i % len(images)]] * clf.n_inputs)

    def timed(fn) -> float:
        start = time.perf_counter()
        fn()
        return (time.perf_counter() - start) * 1000

    photo = [timed(lambda i=i: clf.predict_one(*[images[i % len(images)]] * clf.n_inputs))
             for i in range(runs)]
    case = [timed(lambda i=i: clf.predict_case(images[(2 * i) % len(images)],
                                               images[(2 * i + 1) % len(images)]))
            for i in range(runs // 2)]

    def concurrent_cases(with_decoding: bool) -> list[float]:
        per_thread = max(1, runs // (2 * concurrent))
        workers = [TFLiteClassifier(model_path, threads) for _ in range(concurrent)]
        for w in workers:
            w.predict_one(*one)
        barrier = threading.Barrier(concurrent)
        out: list[float] = []
        lock = threading.Lock()

        def work(k: int) -> None:
            barrier.wait()
            for i in range(per_thread):
                a, b = (2 * (i + k)) % len(jpegs), (2 * (i + k) + 1) % len(jpegs)
                if with_decoding:
                    ms = timed(lambda: workers[k].predict_case(preprocess(jpegs[a], image_size),
                                                               preprocess(jpegs[b], image_size)))
                else:
                    ms = timed(lambda: workers[k].predict_case(images[a], images[b]))
                with lock:
                    out.append(ms)

        pool = [threading.Thread(target=work, args=(k,)) for k in range(concurrent)]
        for t in pool:
            t.start()
        for t in pool:
            t.join()
        return out

    return {"cpus": cpus, "xnnpack": clf.xnnpack, "photo_ms": percentiles(photo),
            "case_ms": percentiles(case),
            "case_concurrent_ms": percentiles(concurrent_cases(False)),
            "case_full_concurrent_ms": percentiles(concurrent_cases(True))}


_COLD_START = """
import json, os, sys, time
t0 = time.perf_counter()
os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:int(sys.argv[2])])
import numpy as np
from melanoma.serving import TFLiteClassifier
t1 = time.perf_counter()
clf = TFLiteClassifier(sys.argv[1], int(sys.argv[2]))
size = int(sys.argv[3])
clf.predict_one(*[np.zeros((size, size, 3), np.float32)] * clf.n_inputs)
t2 = time.perf_counter()
print(json.dumps({"import_s": t1 - t0, "load_and_first_inference_s": t2 - t1}))
"""


def cold_start(model_path: str | Path, threads: int, image_size: int, runs: int) -> dict[str, Any]:
    """Proceso nuevo: arrancar Python, importar LiteRT, cargar el modelo y la 1.ª inferencia.

    No incluye la descarga desde Cloud Storage, que solo se puede medir en Cloud Run.
    """
    totals, parts = [], []
    for _ in range(runs):
        start = time.perf_counter()
        out = subprocess.run([sys.executable, "-c", _COLD_START, str(model_path), str(threads),
                              str(image_size)], capture_output=True, text=True, check=True)
        totals.append(time.perf_counter() - start)
        parts.append(json.loads(out.stdout.strip().splitlines()[-1]))
    return {"total_s": {**percentiles(totals), "max": float(max(totals))},
            "import_s": float(np.median([p["import_s"] for p in parts])),
            "load_and_first_inference_s": float(np.median([p["load_and_first_inference_s"]
                                                           for p in parts]))}
