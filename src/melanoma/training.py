"""Entrenamiento en dos fases (EXP-02): cabeza con el backbone congelado y luego fine-tuning.

`train_fold` entrena un fold completo: arma los datos, entrena, guarda el modelo y devuelve las
predicciones del fold de validación. `train_fold_isolated` hace lo mismo en un proceso aparte.
La estrategia de desbalance sale de `training.imbalance` (EXP-03). Lo reutiliza EXP-06.

En la fase 2 se detiene por AUC del fold de validación y se queda con la mejor época. Ese mismo
fold da las métricas, lo que las vuelve algo optimistas; afecta igual a todos los candidatos, y
la estimación sin sesgo es la única evaluación en el test (EXP-04).
"""

from __future__ import annotations

import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Callable

import keras
import numpy as np
import pandas as pd
import tensorflow as tf

from melanoma.data.pipeline import limit_images, make_dataset
from melanoma.data.splits import train_val
from melanoma.imbalance import setup as imbalance_setup
from melanoma.models import backbone, build_single_view, unfreeze_backbone

PREDICTION_COLUMNS = ["image_id", "lesion_id", "dx", "label"]


def setup_devices(training_cfg: dict[str, Any]) -> dict[str, Any]:
    """Memoria de GPU bajo demanda, precisión mixta y XLA, solo si hay GPU y la config lo pide.

    En la RTX 5060 con la imagen de NVIDIA, XLA multiplica por ~6 la velocidad de entrenamiento
    de MobileNetV3 (`scripts/benchmark_gpu.py`); en CPU la reduce, así que ahí no se usa.
    """
    gpus = tf.config.list_physical_devices("GPU")
    for gpu in gpus:
        tf.config.experimental.set_memory_growth(gpu, True)
    mixed = bool(gpus) and bool(training_cfg.get("mixed_precision"))
    keras.mixed_precision.set_global_policy("mixed_float16" if mixed else "float32")
    jit = bool(gpus) and bool(training_cfg.get("jit_compile"))
    return {"gpus": [g.name for g in gpus], "mixed_precision": mixed, "jit_compile": jit}


def compile_model(model: keras.Model, learning_rate: float,
                  loss: str | keras.losses.Loss = "binary_crossentropy",
                  jit_compile: bool = False) -> None:
    # HU14 pide registrar por época la pérdida, el AUC-ROC y la sensibilidad en validación. La
    # sensibilidad va con umbral 0.5; el umbral operativo se fija en EXP-04.
    model.compile(optimizer=keras.optimizers.Adam(learning_rate), loss=loss,
                  metrics=[keras.metrics.AUC(name="auc"),
                           keras.metrics.AUC(curve="PR", name="pr_auc"),
                           keras.metrics.Recall(name="recall")],
                  jit_compile=jit_compile)


def train_two_phases(model: keras.Model, train_ds: tf.data.Dataset, val_ds: tf.data.Dataset,
                     training_cfg: dict[str, Any], out_dir: Path,
                     loss: str | keras.losses.Loss = "binary_crossentropy",
                     class_weight: dict[int, float] | None = None,
                     steps_per_epoch: int | None = None,
                     jit_compile: bool = False, verbose: int = 2) -> dict[str, Any]:
    """Fase 1: solo la cabeza. Fase 2: el backbone menos sus BatchNorm, con parada temprana por
    `val_auc`.

    Devuelve el historial por época (una lista por métrica, ambas fases seguidas) y la mejor
    época de la fase 2, cuyos pesos quedan en el modelo. `steps_per_epoch` hace falta cuando
    `train_ds` es infinito (sobremuestreo).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    log = keras.callbacks.CSVLogger(str(out_dir / "historial.csv"), append=True)
    head, finetune = training_cfg["phases"]["head"], training_cfg["phases"]["finetune"]

    backbone(model).trainable = False
    compile_model(model, head["learning_rate"], loss, jit_compile)
    h1 = model.fit(train_ds, validation_data=val_ds, epochs=head["epochs"],
                   steps_per_epoch=steps_per_epoch, class_weight=class_weight, callbacks=[log],
                   shuffle=False, verbose=verbose)

    unfreeze_backbone(model)
    compile_model(model, finetune["learning_rate"], loss, jit_compile)
    early = keras.callbacks.EarlyStopping(monitor="val_auc", mode="max",
                                          patience=training_cfg["early_stopping_patience"],
                                          restore_best_weights=True)
    h2 = model.fit(train_ds, validation_data=val_ds, initial_epoch=head["epochs"],
                   epochs=head["epochs"] + finetune["epochs"], steps_per_epoch=steps_per_epoch,
                   class_weight=class_weight, callbacks=[log, early], shuffle=False,
                   verbose=verbose)
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
               jit_compile: bool = False, verbose: int = 2) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Entrena con los demás folds y predice el fold `fold`. El test nunca entra."""
    seed = cfg["seed"] + fold
    keras.backend.clear_session()
    keras.utils.set_random_seed(seed)

    train_df, val_df = train_val(splits, fold)
    max_images = cfg["data"].get("max_images")
    train_df = limit_images(train_df, max_images, seed)
    val_df = limit_images(val_df, max_images, seed)
    batch = cfg["training"]["batch_size"]
    imbalance = imbalance_setup(cfg["training"], train_df.label.to_numpy())
    train_ds = make_dataset(train_df, images_dir, cfg["data"], batch, training=True, seed=seed,
                            positive_fraction=imbalance["positive_fraction"])
    val_ds = make_dataset(val_df, images_dir, cfg["data"], batch, training=False, seed=seed)
    # Con sobremuestreo, tantos lotes por época como sin él: el mismo cómputo en cada estrategia.
    steps = len(train_df) // batch if imbalance["positive_fraction"] is not None else None

    model = (build or (lambda: build_single_view(cfg["model"], cfg["data"]["image_size"])))()
    start = time.perf_counter()
    info = train_two_phases(model, train_ds, val_ds, cfg["training"], out_dir,
                            loss=imbalance["loss"], class_weight=imbalance["class_weight"],
                            steps_per_epoch=steps, jit_compile=jit_compile, verbose=verbose)
    info["class_weight"] = imbalance["class_weight"]
    info["train_seconds"] = round(time.perf_counter() - start, 1)
    info["n_train_images"] = int(len(train_df))
    model.save(out_dir / "modelo.keras")

    predictions = val_df[PREDICTION_COLUMNS].assign(fold=fold, prob=predict(model, val_ds))
    return predictions.reset_index(drop=True), info


def train_fold_isolated(cfg: dict[str, Any], splits: pd.DataFrame, fold: int, images_dir: Path,
                        out_dir: Path, **kwargs: Any) -> tuple[pd.DataFrame, dict[str, Any]]:
    """`train_fold` en un proceso nuevo, que al terminar devuelve toda su memoria.

    En un solo proceso la RAM crece fold a fold (la caché de imágenes y los modelos compilados con
    XLA no se liberan del todo) hasta que el sistema mata el entrenamiento: pasó en el fold 4 de la
    primera corrida de EXP-02. `build`, si se pasa, debe poder serializarse con pickle (una
    función de módulo, no una lambda).
    """
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(max_workers=1, mp_context=context) as pool:
        return pool.submit(_train_fold_child, cfg, splits, fold, images_dir, out_dir,
                           kwargs).result()


def _train_fold_child(cfg: dict[str, Any], splits: pd.DataFrame, fold: int, images_dir: Path,
                      out_dir: Path, kwargs: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    devices = setup_devices(cfg["training"])   # la precisión mixta es global de cada proceso
    return train_fold(cfg, splits, fold, images_dir, out_dir, jit_compile=devices["jit_compile"],
                      **kwargs)
