"""EXP-06 por fold: una foto frente a dos fotos sobre las mismas lesiones.

`two_view_fold` parte del modelo de una foto del fold (EXP-03 sin balanceo) y predice el par fijo
(A, B) de cada lesión de validación con 2 o más fotos de cinco formas:

- `single_a` y `single_b`: el modelo de una foto con cada foto;
- `average`: el promedio de ambas predicciones (fusión fija, como Hekler et al. 2024);
- `fusion`: el modelo de dos fotos con fusión aprendida, entrenado sobre las lesiones con 2 o más
  fotos de los otros folds;
- `fusion_single`: el mismo modelo de dos fotos con la foto A repetida (el respaldo de una foto).

Para la H3 repite todo con la foto A degradada (desenfoque o poca luz) y la B intacta. También
guarda el peso que la fusión le da a la foto A, para ver si aprendió a desconfiar de la mala.

Con `metadata.use` (EXP-07) la fusión recibe además la edad, el sexo y la zona del cuerpo de la
lesión (los de su primera foto), que suman al logit de las fotos.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import keras
import numpy as np
import pandas as pd
import tensorflow as tf

from melanoma.data import metadata as patient
from melanoma.data.pipeline import AUTOTUNE
from melanoma.data.splits import train_val
from melanoma.data.views import degrade, fixed_pairs, load_images, multi_image_lesions, training_pairs
from melanoma.models import build_single_view, build_two_view, view_weights, with_metadata
from melanoma.runs import PROJECT_ROOT
from melanoma.training import train_two_phases


def degradations(cfg: dict[str, Any]) -> list[tuple[str, str, float]]:
    """[(nombre, tipo, nivel)] de `evaluation_degradations`, p. ej. ("blur_4", "blur", 4.0)."""
    return [(f"{kind}_{level:g}", kind, float(level))
            for kind, levels in cfg["evaluation_degradations"].items() for level in levels]


def limit_lesions(df: pd.DataFrame, max_lesions: int | None, seed: int) -> pd.DataFrame:
    """Muestra estratificada de lesiones, con todas sus fotos (solo para pruebas rápidas)."""
    if not max_lesions:
        return df
    lesions = df.drop_duplicates("lesion_id")
    if len(lesions) <= max_lesions:
        return df
    frac = max_lesions / len(lesions)
    keep = lesions.groupby("label", group_keys=False).sample(frac=frac, random_state=seed).lesion_id
    return df[df.lesion_id.isin(keep)]


def _batches(*arrays: np.ndarray, batch_size: int) -> tf.data.Dataset:
    ds = tf.data.Dataset.from_tensor_slices(arrays)
    return ds.batch(batch_size).map(lambda *x: tuple(tf.cast(v, tf.float32) for v in x),
                                    num_parallel_calls=AUTOTUNE).prefetch(AUTOTUNE)


def predict_single(model: keras.Model, images: np.ndarray, batch_size: int) -> np.ndarray:
    ds = tf.data.Dataset.from_tensor_slices(images).batch(batch_size)
    ds = ds.map(lambda x: tf.cast(x, tf.float32), num_parallel_calls=AUTOTUNE)
    return model.predict(ds, verbose=0).astype("float64").ravel()


def _pair_inputs(a: np.ndarray, b: np.ndarray, meta: np.ndarray | None,
                 batch_size: int) -> tf.data.Dataset:
    if meta is None:
        return _batches(a, b, batch_size=batch_size).map(lambda x, y: {"view_a": x, "view_b": y})
    return _batches(a, b, meta, batch_size=batch_size).map(
        lambda x, y, m: {"view_a": x, "view_b": y, "metadata": m})


def predict_pair(model: keras.Model, a: np.ndarray, b: np.ndarray, batch_size: int,
                 meta: np.ndarray | None = None) -> np.ndarray:
    return model.predict(_pair_inputs(a, b, meta, batch_size), verbose=0).astype("float64").ravel()


def lesion_metadata(df: pd.DataFrame, lesion_ids, table: pd.DataFrame) -> np.ndarray:
    """Datos del paciente de cada lesión: los de su primera foto (por `image_id`)."""
    first = df.sort_values("image_id").drop_duplicates("lesion_id").set_index("lesion_id").image_id
    return patient.for_images(first.loc[list(lesion_ids)], table)


def degraded_copy(images: np.ndarray, kind: str, level: float, chunk: int = 64) -> np.ndarray:
    """La foto degradada vuelve a uint8, como llegaría una foto mala real."""
    out = np.empty_like(images)
    for i in range(0, len(images), chunk):
        bad = degrade(images[i:i + chunk], kind, level).numpy()
        out[i:i + chunk] = np.clip(np.round(bad), 0, 255).astype(np.uint8)
    return out


def two_view_fold(cfg: dict[str, Any], splits: pd.DataFrame, fold: int, images_dir: Path,
                  single_model_path: Path, out_dir: Path, jit_compile: bool = False,
                  verbose: int = 2) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Entrena la fusión con los otros folds y predice las lesiones de `fold` (una fila por lesión)."""
    seed = cfg["seed"] + fold
    keras.backend.clear_session()
    keras.utils.set_random_seed(seed)
    size, batch = cfg["data"]["image_size"], cfg["training"]["batch_size"]
    max_lesions = cfg["pairs"].get("max_lesions")

    train_df, val_df = train_val(splits, fold)
    train_df = limit_lesions(multi_image_lesions(train_df), max_lesions, seed)
    val_pairs = fixed_pairs(limit_lesions(multi_image_lesions(val_df), max_lesions, seed), seed)

    single = build_single_view(cfg["model"], size, weights=None)
    single.load_weights(single_model_path)

    train_ids = train_df.image_id.unique()
    train_images = load_images(train_ids, images_dir, size)
    row = {image_id: k for k, image_id in enumerate(train_ids)}
    lesions = train_df.groupby("lesion_id", sort=True)
    groups = [np.array([row[i] for i in g.image_id]) for _, g in lesions]
    labels = lesions.label.first().to_numpy()
    view_a = load_images(val_pairs.image_a, images_dir, size)
    view_b = load_images(val_pairs.image_b, images_dir, size)
    meta_cfg = cfg.get("metadata") or {}
    train_meta = val_meta = None
    if meta_cfg.get("use"):
        table = patient.load(PROJECT_ROOT / cfg["data"]["sources"]["ham10000"]["metadata"])
        train_meta = lesion_metadata(train_df, [lesion for lesion, _ in lesions], table)
        val_meta = lesion_metadata(val_df, val_pairs.lesion_id, table)
    bad = {name: degraded_copy(view_a, kind, level) for name, kind, level in degradations(cfg)}

    # Primero el modelo de una foto: la fusión comparte su backbone y lo cambia al entrenar.
    pred = val_pairs.assign(fold=fold)
    pred["single_a"] = predict_single(single, view_a, batch)
    pred["single_b"] = predict_single(single, view_b, batch)
    pred["average"] = (pred.single_a + pred.single_b) / 2
    for name, images in bad.items():
        pred[f"single_a_{name}"] = predict_single(single, images, batch)
        pred[f"average_{name}"] = (pred[f"single_a_{name}"] + pred.single_b) / 2

    model = build_two_view(single, cfg["fusion"])
    if meta_cfg.get("use"):
        model = with_metadata(model, patient.N_FEATURES, meta_cfg.get("hidden", 32))
    train_ds = training_pairs(train_images, groups, labels, cfg["data"],
                              cfg.get("view_degradation"), batch, seed, metadata=train_meta)
    val_labels = tf.data.Dataset.from_tensor_slices(val_pairs.label.to_numpy(dtype="float32"))
    val_ds = tf.data.Dataset.zip((_pair_inputs(view_a, view_b, val_meta, batch).unbatch(),
                                  val_labels)).batch(batch)
    start = time.perf_counter()
    info = train_two_phases(model, train_ds, val_ds, cfg["training"], out_dir,
                            steps_per_epoch=max(1, len(groups) // batch), jit_compile=jit_compile,
                            verbose=verbose)
    info["train_seconds"] = round(time.perf_counter() - start, 1)
    info.update(n_train_lesions=len(groups), n_train_images=len(train_ids), n_val_lesions=len(pred))
    model.save(out_dir / "modelo.keras")

    weights = view_weights(model)
    pred["fusion"] = predict_pair(model, view_a, view_b, batch, val_meta)
    pred["fusion_single"] = predict_pair(model, view_a, view_a, batch, val_meta)
    pred["weight_a"] = predict_weights(weights, view_a, view_b, batch, val_meta)
    for name, images in bad.items():
        pred[f"fusion_{name}"] = predict_pair(model, images, view_b, batch, val_meta)
        pred[f"weight_a_{name}"] = predict_weights(weights, images, view_b, batch, val_meta)
    return pred, info


def predict_weights(weights: keras.Model, a: np.ndarray, b: np.ndarray, batch_size: int,
                    meta: np.ndarray | None = None) -> np.ndarray:
    """Peso que la fusión le da a la foto A (el de B es 1 menos ese)."""
    return weights.predict(_pair_inputs(a, b, meta, batch_size), verbose=0)[:, 0].astype("float64")
