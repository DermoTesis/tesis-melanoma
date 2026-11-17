"""Pares de fotos de una misma lesión y degradación de una vista (EXP-06).

HAM10000 tiene lesiones con varias fotos dermatoscópicas: con distinto aumento, ángulo o cámara.
EXP-06 usa solo esas lesiones, así las de una foto y las de dos se comparan sobre las mismas
lesiones y el número de fotos no puede delatar el diagnóstico (63% de los melanomas tiene 2 o más
fotos, frente a 18% de los nevus).

- En entrenamiento, cada época toma 2 fotos distintas al azar de cada lesión.
- En validación, cada lesión tiene un par fijo (A, B), elegido al azar con la semilla.
- `degrade` simula una foto mala (desenfoque o poca luz) para enseñar y medir la robustez (H3).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd
import tensorflow as tf

from melanoma.data.pipeline import AUTOTUNE, augmenter, load_image


def multi_image_lesions(df: pd.DataFrame) -> pd.DataFrame:
    """Solo las imágenes de lesiones con 2 o más fotos."""
    return df[df.groupby("lesion_id").image_id.transform("size") >= 2]


def fixed_pairs(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Un par (A, B) por lesión con 2 o más fotos: dos fotos distintas elegidas al azar.

    Devuelve una fila por lesión con `image_a`, `image_b`, `lesion_id`, `label`, `dx` y `dataset`.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for lesion_id, group in multi_image_lesions(df).sort_values("image_id").groupby("lesion_id"):
        a, b = rng.choice(group.image_id.to_numpy(), size=2, replace=False)
        first = group.iloc[0]
        rows.append({"lesion_id": lesion_id, "image_a": a, "image_b": b, "label": int(first.label),
                     "dx": first.dx, "dataset": first.get("dataset")})
    return pd.DataFrame(rows)


def load_images(image_ids: Sequence[str], images_dir: str | Path, image_size: int) -> np.ndarray:
    """uint8 (n, image_size, image_size, 3), con el mismo preprocesamiento que el entrenamiento."""
    paths = [str(Path(images_dir) / f"{i}.jpg") for i in image_ids]
    if not paths:
        return np.zeros((0, image_size, image_size, 3), np.uint8)
    ds = tf.data.Dataset.from_tensor_slices(paths).map(lambda p: load_image(p, image_size),
                                                       num_parallel_calls=AUTOTUNE)
    return np.concatenate(list(ds.batch(256).as_numpy_iterator()))


def gaussian_blur(images: tf.Tensor, sigma: float) -> tf.Tensor:
    """Desenfoque gaussiano (float32, lote), con los bordes reflejados."""
    radius = max(1, int(math.ceil(3 * sigma)))
    x = tf.range(-radius, radius + 1, dtype=tf.float32)
    kernel = tf.exp(-(x ** 2) / (2 * sigma ** 2))
    kernel /= tf.reduce_sum(kernel)
    channels = 3
    horizontal = tf.tile(tf.reshape(kernel, (1, -1, 1, 1)), (1, 1, channels, 1))
    vertical = tf.tile(tf.reshape(kernel, (-1, 1, 1, 1)), (1, 1, channels, 1))
    padded = tf.pad(images, [[0, 0], [radius, radius], [radius, radius], [0, 0]], mode="REFLECT")
    out = tf.nn.depthwise_conv2d(padded, horizontal, strides=(1, 1, 1, 1), padding="VALID")
    return tf.nn.depthwise_conv2d(out, vertical, strides=(1, 1, 1, 1), padding="VALID")


def degrade(images: tf.Tensor | np.ndarray, kind: str, level: float) -> tf.Tensor:
    """Foto mala: `blur` (desenfoque con sigma = level, en píxeles) o `dark` (brillo × level)."""
    images = tf.cast(images, tf.float32)
    if kind == "blur":
        return gaussian_blur(images, level)
    if kind == "dark":
        return images * level
    raise ValueError(f"Degradación desconocida {kind!r}: blur o dark")


def random_view_degradation(cfg: dict[str, Any]):
    """Función de lote que, con probabilidad `probability`, degrada una de las dos vistas al azar.

    El tipo (desenfoque o poca luz) se elige por imagen; el sigma y el factor de brillo, por lote.
    Así la fusión aprende a quitarle peso a una foto mala sin perder la otra.
    """
    sigmas = [float(s) for s in cfg["blur_sigmas"]]
    low, high = (float(v) for v in cfg["dark_factor"])
    p = float(cfg["probability"])

    def apply(a: tf.Tensor, b: tf.Tensor) -> tuple[tf.Tensor, tf.Tensor]:
        n = tf.shape(a)[0]
        chosen = tf.random.uniform([n]) < p
        on_a = tf.random.uniform([n]) < 0.5
        use_blur = (tf.random.uniform([n]) < 0.5)[:, None, None, None]
        index = tf.random.uniform([], 0, len(sigmas), dtype=tf.int32)
        factor = tf.random.uniform([], low, high)

        def bad(x: tf.Tensor) -> tf.Tensor:
            blurred = tf.switch_case(index, [lambda s=s: gaussian_blur(x, s) for s in sigmas])
            return tf.where(use_blur, blurred, x * factor)

        a = tf.where((chosen & on_a)[:, None, None, None], bad(a), a)
        b = tf.where((chosen & ~on_a)[:, None, None, None], bad(b), b)
        return a, b

    return apply


def random_image_degradation(cfg: dict[str, Any]):
    """Función de lote que degrada cada imagen con probabilidad `probability` (EXP-10).

    Mismos tipos y niveles que `random_view_degradation`, pero para el modelo de una foto: el tipo
    se elige por imagen y el sigma y el factor de brillo, por lote.
    """
    sigmas = [float(s) for s in cfg["blur_sigmas"]]
    low, high = (float(v) for v in cfg["dark_factor"])
    p = float(cfg["probability"])

    def apply(x: tf.Tensor) -> tf.Tensor:
        n = tf.shape(x)[0]
        chosen = (tf.random.uniform([n]) < p)[:, None, None, None]
        use_blur = (tf.random.uniform([n]) < 0.5)[:, None, None, None]
        index = tf.random.uniform([], 0, len(sigmas), dtype=tf.int32)
        factor = tf.random.uniform([], low, high)
        blurred = tf.switch_case(index, [lambda s=s: gaussian_blur(x, s) for s in sigmas])
        return tf.where(chosen, tf.where(use_blur, blurred, x * factor), x)

    return apply


def training_pairs(images: np.ndarray, groups: list[np.ndarray], labels: np.ndarray,
                   data_cfg: dict[str, Any], degradation_cfg: dict[str, Any] | None,
                   batch_size: int, seed: int, metadata: np.ndarray | None = None) -> tf.data.Dataset:
    """Flujo infinito de lotes ({"view_a", "view_b"[, "metadata"]}, etiqueta) para la fusión.

    `groups[i]` son las filas de `images` de la lesión i (2 o más), `labels[i]` su etiqueta y
    `metadata[i]`, si se pasa, sus datos del paciente (EXP-07). Cada vista recibe su propio
    aumento de datos, como dos tomas distintas.
    """
    rng = np.random.default_rng(seed)
    size = images.shape[1]
    extra = np.zeros((len(groups), 0), np.float32) if metadata is None else metadata

    def generate():
        while True:
            for i in rng.permutation(len(groups)):
                a, b = rng.choice(groups[i], size=2, replace=False)
                yield images[a], images[b], extra[i], np.float32(labels[i])

    spec = tf.TensorSpec((size, size, 3), tf.uint8)
    ds = tf.data.Dataset.from_generator(
        generate, output_signature=(spec, spec, tf.TensorSpec((extra.shape[1],), tf.float32),
                                    tf.TensorSpec((), tf.float32)))
    ds = ds.batch(batch_size, drop_remainder=True)
    ds = ds.map(lambda a, b, m, y: (tf.cast(a, tf.float32), tf.cast(b, tf.float32), m, y),
                num_parallel_calls=AUTOTUNE)
    aug = augmenter(data_cfg.get("augmentation") or {}, seed)
    if aug is not None:
        ds = ds.map(lambda a, b, m, y: (aug(a, training=True), aug(b, training=True), m, y),
                    num_parallel_calls=AUTOTUNE)
    if degradation_cfg and degradation_cfg.get("probability"):
        bad = random_view_degradation(degradation_cfg)
        ds = ds.map(lambda a, b, m, y: (*bad(a, b), m, y), num_parallel_calls=AUTOTUNE)
    if metadata is None:
        ds = ds.map(lambda a, b, m, y: ({"view_a": a, "view_b": b}, y))
    else:
        ds = ds.map(lambda a, b, m, y: ({"view_a": a, "view_b": b, "metadata": m}, y))
    return ds.prefetch(AUTOTUNE)
