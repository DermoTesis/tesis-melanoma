"""Entrenamiento en dos fases (EXP-02): cabeza con el backbone congelado y luego fine-tuning.

`train_fold` entrena un fold completo: arma los datos, entrena, guarda el modelo y devuelve las
predicciones del fold de validación. Lo reutilizan EXP-03 (con otra pérdida o pesos de clase) y
EXP-06.

En la fase 2 se detiene por AUC del fold de validación y se queda con la mejor época. Ese mismo
fold da las métricas, lo que las vuelve algo optimistas; afecta igual a todos los candidatos, y
la estimación sin sesgo es la única evaluación en el test (EXP-04).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import keras
import numpy as np
import pandas as pd
import tensorflow as tf

from melanoma.data.pipeline import limit_images, make_dataset
from melanoma.data.splits import train_val
from melanoma.models import backbone, build_single_view

PREDICTION_COLUMNS = ["image_id", "lesion_id", "dx", "label"]


def setup_devices(training_cfg: dict[str, Any]) -> dict[str, Any]:
    """Memoria de GPU bajo demanda y precisión mixta (solo si hay GPU y la config lo pide)."""
    gpus = tf.config.list_physical_devices("GPU")
    for gpu in gpus:
        tf.config.experimental.set_memory_growth(gpu, True)
    mixed = bool(gpus) and bool(training_cfg.get("mixed_precision"))
    keras.mixed_precision.set_global_policy("mixed_float16" if mixed else "float32")
    return {"gpus": [g.name for g in gpus], "mixed_precision": mixed}


def compile_model(model: keras.Model, learning_rate: float,
                  loss: str | keras.losses.Loss = "binary_crossentropy") -> None:
    model.compile(optimizer=keras.optimizers.Adam(learning_rate), loss=loss,
                  metrics=[keras.metrics.AUC(name="auc"),
                           keras.metrics.AUC(curve="PR", name="pr_auc")])


def train_two_phases(model: keras.Model, train_ds: tf.data.Dataset, val_ds: tf.data.Dataset,
                     training_cfg: dict[str, Any], out_dir: Path,
                     loss: str | keras.losses.Loss = "binary_crossentropy",
                     class_weight: dict[int, float] | None = None,
                     verbose: int = 2) -> dict[str, Any]:
    """Fase 1: solo la cabeza. Fase 2: todo el backbone, con parada temprana por `val_auc`.

    Devuelve el historial por época (una lista por métrica, ambas fases seguidas) y la mejor
    época de la fase 2, cuyos pesos quedan en el modelo.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    log = keras.callbacks.CSVLogger(str(out_dir / "historial.csv"), append=True)
    head, finetune = training_cfg["phases"]["head"], training_cfg["phases"]["finetune"]

    backbone(model).trainable = False
    compile_model(model, head["learning_rate"], loss)
    h1 = model.fit(train_ds, validation_data=val_ds, epochs=head["epochs"],
                   class_weight=class_weight, callbacks=[log], shuffle=False, verbose=verbose)

    backbone(model).trainable = True
    compile_model(model, finetune["learning_rate"], loss)
    early = keras.callbacks.EarlyStopping(monitor="val_auc", mode="max",
                                          patience=training_cfg["early_stopping_patience"],
                                          restore_best_weights=True)
    h2 = model.fit(train_ds, validation_data=val_ds, initial_epoch=head["epochs"],
                   epochs=head["epochs"] + finetune["epochs"], class_weight=class_weight,
                   callbacks=[log, early], shuffle=False, verbose=verbose)
    # Algunas versiones de Keras solo restauran si la parada fue temprana: se fuerza aquí.
    if early.best_weights is not None:
        model.set_weights(early.best_weights)

    history = {k: [float(v) for v in h1.history.get(k, [])] + [float(v) for v in vals]
               for k, vals in h2.history.items()}
    best = int(np.argmax(h2.history["val_auc"]))
    return {"history": history, "head_epochs": len(h1.history["loss"]),
            "finetune_epochs": len(h2.history["loss"]), "best_epoch": head["epochs"] + best + 1,
            "best_val_auc_keras": float(h2.history["val_auc"][best])}


def predict(model: keras.Model, ds: tf.data.Dataset) -> np.ndarray:
    return model.predict(ds, verbose=0).astype("float64").ravel()


def train_fold(cfg: dict[str, Any], splits: pd.DataFrame, fold: int, images_dir: Path,
               out_dir: Path, build: Callable[[], keras.Model] | None = None,
               loss: str | keras.losses.Loss = "binary_crossentropy",
               class_weight: dict[int, float] | None = None,
               verbose: int = 2) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Entrena con los demás folds y predice el fold `fold`. El test nunca entra."""
    seed = cfg["seed"] + fold
    keras.backend.clear_session()
    keras.utils.set_random_seed(seed)

    train_df, val_df = train_val(splits, fold)
    max_images = cfg["data"].get("max_images")
    train_df = limit_images(train_df, max_images, seed)
    val_df = limit_images(val_df, max_images, seed)
    batch = cfg["training"]["batch_size"]
    train_ds = make_dataset(train_df, images_dir, cfg["data"], batch, training=True, seed=seed)
    val_ds = make_dataset(val_df, images_dir, cfg["data"], batch, training=False, seed=seed)

    model = (build or (lambda: build_single_view(cfg["model"], cfg["data"]["image_size"])))()
    start = time.perf_counter()
    info = train_two_phases(model, train_ds, val_ds, cfg["training"], out_dir, loss=loss,
                            class_weight=class_weight, verbose=verbose)
    info["train_seconds"] = round(time.perf_counter() - start, 1)
    info["n_train_images"] = int(len(train_df))
    model.save(out_dir / "modelo.keras")

    predictions = val_df[PREDICTION_COLUMNS].assign(fold=fold, prob=predict(model, val_ds))
    return predictions.reset_index(drop=True), info
