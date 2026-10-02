"""Lectura de imágenes con tf.data (EXP-02 en adelante).

Cada imagen se decodifica, se redimensiona completa a `image_size` × `image_size` y se guarda como
uint8 (en RAM si `cache`). El modelo recibe float32 en rango 0-255. El aumento de datos se aplica
después de la caché, así que cambia en cada época.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import keras
import pandas as pd
import tensorflow as tf

AUTOTUNE = tf.data.AUTOTUNE


def load_image(path: tf.Tensor, image_size: int) -> tf.Tensor:
    """JPEG → uint8 (image_size, image_size, 3). Es el mismo preprocesamiento del backend."""
    image = tf.io.decode_jpeg(tf.io.read_file(path), channels=3)
    image = tf.image.resize(image, (image_size, image_size), method="bilinear", antialias=True)
    return tf.cast(tf.clip_by_value(tf.round(image), 0, 255), tf.uint8)


def augmenter(cfg: dict[str, Any], seed: int) -> keras.Sequential | None:
    """Capas de aumento de datos según `data.augmentation`; None si no hay ninguna.

    Van en float32 aunque la política global sea de precisión mixta: corren en la CPU, dentro de
    tf.data, no en el modelo.
    """
    L = keras.layers
    common = {"seed": seed, "dtype": "float32"}
    layers = []
    if cfg.get("flip"):
        layers.append(L.RandomFlip("horizontal_and_vertical", **common))
    if cfg.get("rotation"):
        layers.append(L.RandomRotation(cfg["rotation"], fill_mode="reflect", **common))
    if cfg.get("zoom"):
        # En Keras, un factor negativo es acercar: (-zoom, 0) acerca hasta `zoom` y nunca aleja.
        layers.append(L.RandomZoom((-cfg["zoom"], 0.0), fill_mode="reflect", **common))
    if cfg.get("brightness"):
        layers.append(L.RandomBrightness(cfg["brightness"], value_range=(0, 255), **common))
    if cfg.get("contrast"):
        layers.append(L.RandomContrast(cfg["contrast"], value_range=(0, 255), **common))
    return keras.Sequential(layers, name="augmentation") if layers else None


def make_dataset(df: pd.DataFrame, images_dir: str | Path, data_cfg: dict[str, Any],
                 batch_size: int, training: bool, seed: int) -> tf.data.Dataset:
    """(imagen float32 0-255, etiqueta float32) por lotes.

    En entrenamiento baraja en cada época y aplica el aumento de datos; en evaluación respeta el
    orden de `df`, para poder unir las predicciones con sus `image_id`.
    """
    images_dir = Path(images_dir)
    paths = [str(images_dir / f"{image_id}.jpg") for image_id in df.image_id]
    labels = df.label.to_numpy(dtype="float32")
    size = data_cfg["image_size"]

    ds = tf.data.Dataset.from_tensor_slices((paths, labels))
    ds = ds.map(lambda p, y: (load_image(p, size), y), num_parallel_calls=AUTOTUNE)
    if data_cfg.get("cache"):
        ds = ds.cache()
    if training:
        ds = ds.shuffle(len(df), seed=seed, reshuffle_each_iteration=True)
    # En entrenamiento se descarta el último lote incompleto (cambia en cada época por el
    # barajado): con XLA, cada tamaño de lote distinto obliga a recompilar el modelo.
    ds = ds.batch(batch_size, drop_remainder=training)
    ds = ds.map(lambda x, y: (tf.cast(x, tf.float32), y), num_parallel_calls=AUTOTUNE)
    aug = augmenter(data_cfg.get("augmentation") or {}, seed) if training else None
    if aug is not None:
        ds = ds.map(lambda x, y: (aug(x, training=True), y), num_parallel_calls=AUTOTUNE)
    return ds.prefetch(AUTOTUNE)


def limit_images(df: pd.DataFrame, max_images: int | None, seed: int) -> pd.DataFrame:
    """Muestra estratificada por etiqueta, para pruebas rápidas (`data.max_images`)."""
    if not max_images or len(df) <= max_images:
        return df
    frac = max_images / len(df)
    sample = df.groupby("label", group_keys=False).sample(frac=frac, random_state=seed)
    return sample.sort_values("image_id")
