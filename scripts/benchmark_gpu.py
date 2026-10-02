"""Mide la velocidad real de la GPU con varias variantes, para ubicar cuellos de botella.

    python scripts/benchmark_gpu.py [--steps 15] [--batch-size 32]

Cada variante entrena con `model.fit` sobre un lote fijo (sin leer imágenes), así que mide solo
la GPU: multiplicación de matrices (TFLOPS) y MobileNetV3-Large en float32, en precisión mixta y
con XLA, y ResNet50 en precisión mixta, que no usa convoluciones depthwise. Sin pesos de ImageNet
(no cambian la velocidad).
"""

from __future__ import annotations

import argparse
import time

import numpy as np
import tensorflow as tf

for _gpu in tf.config.list_physical_devices("GPU"):
    tf.config.experimental.set_memory_growth(_gpu, True)

import keras  # noqa: E402


def matmul_tflops(dtype: str, n: int = 4096, reps: int = 20) -> float:
    a = tf.random.normal((n, n), dtype=dtype)
    b = tf.random.normal((n, n), dtype=dtype)

    @tf.function
    def run():
        c = a
        for _ in range(reps):
            c = tf.matmul(c, b) / n
        return tf.reduce_sum(tf.cast(c, tf.float32))

    run().numpy()
    t0 = time.perf_counter()
    run().numpy()
    return 2 * n**3 * reps / (time.perf_counter() - t0) / 1e12


def train_speed(build, policy: str, jit: bool | str, steps: int, batch: int) -> tuple[float, float]:
    keras.backend.clear_session()
    keras.mixed_precision.set_global_policy(policy)
    base = build()
    out = keras.layers.Dense(1, activation="sigmoid", dtype="float32")(base.output)
    model = keras.Model(base.input, out)
    model.compile(optimizer=keras.optimizers.Adam(1e-4), loss="binary_crossentropy",
                  jit_compile=jit)
    rng = np.random.default_rng(0)
    x = rng.uniform(0, 255, (batch, 224, 224, 3)).astype("float32")
    y = rng.integers(0, 2, (batch, 1)).astype("float32")
    ds = tf.data.Dataset.from_tensors((x, y)).repeat()
    t0 = time.perf_counter()
    model.fit(ds, epochs=1, steps_per_epoch=3, shuffle=False, verbose=0)
    warmup = time.perf_counter() - t0
    t0 = time.perf_counter()
    model.fit(ds, epochs=1, steps_per_epoch=steps, shuffle=False, verbose=0)
    return batch * steps / (time.perf_counter() - t0), warmup


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--steps", type=int, default=15)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    print(f"TensorFlow {tf.__version__}, Keras {keras.__version__}, "
          f"GPU: {[g.name for g in tf.config.list_physical_devices('GPU')]}")
    print(f"matmul float32: {matmul_tflops('float32'):.1f} TFLOPS")
    print(f"matmul float16: {matmul_tflops('float16'):.1f} TFLOPS")

    v3 = lambda: keras.applications.MobileNetV3Large(  # noqa: E731
        input_shape=(224, 224, 3), include_top=False, weights=None, pooling="avg")
    r50 = lambda: keras.applications.ResNet50(  # noqa: E731
        input_shape=(224, 224, 3), include_top=False, weights=None, pooling="avg")
    variants = [("MobileNetV3-Large float32", v3, "float32", False),
                ("MobileNetV3-Large mixta", v3, "mixed_float16", False),
                ("MobileNetV3-Large mixta + XLA", v3, "mixed_float16", True),
                ("ResNet50 mixta", r50, "mixed_float16", False)]
    for name, build, policy, jit in variants:
        try:
            speed, warmup = train_speed(build, policy, jit, args.steps, args.batch_size)
            print(f"{name:32s} {speed:8.1f} img/s   (compilación {warmup:5.1f} s)", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"{name:32s} ERROR {type(exc).__name__}: {str(exc)[:300]}", flush=True)


if __name__ == "__main__":
    main()
