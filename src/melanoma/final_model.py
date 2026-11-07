"""Modelo final de EXP-04: el de una foto y el de dos fotos, entrenados con todo train + val.

Con todos los datos no queda validación para detenerse, así que cada fase entrena las épocas que
salieron de la validación cruzada (la mediana de la mejor época de los folds; ver
`experiments/exp04_modelo_final.py`). El test no entra.

1. El modelo de una foto con todas las imágenes de train + val, como EXP-03 sin balanceo.
2. Se guarda, y desde él se arma y entrena la fusión de dos fotos con todas las lesiones de train
   + val con 2 o más fotos, como EXP-06. La fusión comparte el backbone y lo cambia, por eso el
   de una foto se guarda antes.
"""

from __future__ import annotations

import copy
import time
from pathlib import Path
from typing import Any

import keras
import numpy as np
import pandas as pd

from melanoma.data.pipeline import limit_images, make_dataset
from melanoma.data.splits import TRAINVAL
from melanoma.data.views import load_images, multi_image_lesions, training_pairs
from melanoma.imbalance import loss_only
from melanoma.models import build_single_view, build_two_view
from melanoma.multiview import limit_lesions
from melanoma.training import train_two_phases


def train_final(cfg: dict[str, Any], splits: pd.DataFrame, images_dir: Path, out_dir: Path,
                jit_compile: bool = False, verbose: int = 2) -> dict[str, Any]:
    """Entrena y guarda `una_foto.keras` y `dos_fotos.keras` en `out_dir`."""
    seed = cfg["seed"]
    keras.backend.clear_session()
    keras.utils.set_random_seed(seed)
    trainval = splits[splits.split == TRAINVAL]
    max_images = cfg["data"].get("max_images")   # solo para pruebas rápidas
    size, batch = cfg["data"]["image_size"], cfg["training"]["batch_size"]
    info: dict[str, Any] = {}

    single_cfg = copy.deepcopy(cfg["training"])
    single_cfg["phases"] = cfg["final"]["single_view"]["phases"]
    single = build_single_view(cfg["model"], size)
    single_df = limit_images(trainval, max_images, seed)
    train_ds = make_dataset(single_df, images_dir, cfg["data"], batch, training=True, seed=seed)
    start = time.perf_counter()
    loss = loss_only(cfg["training"])   # BCE salvo que EXP-08 adopte otra pérdida
    info["single_view"] = train_two_phases(single, train_ds, None, single_cfg,
                                           out_dir / "una_foto", loss=loss,
                                           jit_compile=jit_compile, verbose=verbose)
    info["single_view"].update(train_seconds=round(time.perf_counter() - start, 1),
                               n_train_images=int(len(single_df)))
    single.save(out_dir / "una_foto.keras")
    del train_ds

    two_cfg = copy.deepcopy(cfg["training"])
    two_cfg["phases"] = cfg["final"]["two_view"]["phases"]
    multi = limit_lesions(multi_image_lesions(trainval), max_images, seed)
    image_ids = multi.image_id.unique()
    images = load_images(image_ids, images_dir, size)
    row = {image_id: k for k, image_id in enumerate(image_ids)}
    lesions = multi.groupby("lesion_id", sort=True)
    groups = [np.array([row[i] for i in g.image_id]) for _, g in lesions]
    labels = lesions.label.first().to_numpy()
    model = build_two_view(single, cfg["fusion"])
    pairs_ds = training_pairs(images, groups, labels, cfg["data"], cfg.get("view_degradation"),
                              batch, seed)
    start = time.perf_counter()
    info["two_view"] = train_two_phases(model, pairs_ds, None, two_cfg, out_dir / "dos_fotos",
                                        loss=loss, steps_per_epoch=max(1, len(groups) // batch),
                                        jit_compile=jit_compile, verbose=verbose)
    info["two_view"].update(train_seconds=round(time.perf_counter() - start, 1),
                            n_train_lesions=len(groups), n_train_images=int(len(image_ids)))
    model.save(out_dir / "dos_fotos.keras")
    return info
