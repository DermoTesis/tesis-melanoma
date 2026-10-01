"""Metadatos de HAM10000 y etiqueta binaria (EXP-01).

El CSV de Harvard Dataverse trae una fila por imagen con `lesion_id`, `image_id`, `dx` (7 clases),
`dx_type` (cómo se confirmó el diagnóstico), `age`, `sex`, `localization` y `dataset` (la fuente
dentro de HAM10000: vidir_modern, vidir_molemax, rosendahl o vienna_dias).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

import pandas as pd

CLASSES = ("akiec", "bcc", "bkl", "df", "mel", "nv", "vasc")
COLUMNS = ("lesion_id", "image_id", "dx", "dx_type", "age", "sex", "localization", "dataset")


class MetadataError(ValueError):
    """Los metadatos no cumplen lo que la partición y el entrenamiento suponen."""


def file_md5(path: str | Path) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_metadata(path: str | Path, positive_classes: Iterable[str] = ("mel",),
                  expected_md5: str | None = None) -> pd.DataFrame:
    """Lee y valida los metadatos; agrega `label` (1 si `dx` está en `positive_classes`)."""
    path = Path(path)
    if expected_md5 is not None and (actual := file_md5(path)) != expected_md5:
        raise MetadataError(f"{path} tiene md5 {actual}, se esperaba {expected_md5}: "
                            "no es la versión de los metadatos con la que se congeló la partición")
    positive = set(positive_classes)
    if not positive or positive - set(CLASSES):
        raise MetadataError(f"Clases positivas inválidas {sorted(positive)}; válidas: {CLASSES}")

    meta = pd.read_csv(path)
    missing = [c for c in COLUMNS if c not in meta.columns]
    if missing:
        raise MetadataError(f"Faltan columnas en {path.name}: {missing}")
    if meta.image_id.duplicated().any():
        raise MetadataError(f"image_id repetidos: {meta.image_id[meta.image_id.duplicated()].tolist()[:5]}")
    if meta.lesion_id.isna().any():
        raise MetadataError(f"{int(meta.lesion_id.isna().sum())} imágenes sin lesion_id")
    unknown = sorted(set(meta.dx) - set(CLASSES))
    if unknown:
        raise MetadataError(f"Diagnósticos desconocidos: {unknown}")
    mixed = meta.groupby("lesion_id").dx.nunique()
    if (mixed > 1).any():
        raise MetadataError(f"Lesiones con más de un diagnóstico: {mixed[mixed > 1].index.tolist()[:5]}")

    meta["label"] = meta.dx.isin(positive).astype(int)
    return meta.sort_values("image_id").reset_index(drop=True)


def missing_images(meta: pd.DataFrame, images_dir: str | Path) -> list[str]:
    """`image_id` sin su `.jpg` en `images_dir`."""
    images_dir = Path(images_dir)
    return [i for i in meta.image_id if not (images_dir / f"{i}.jpg").is_file()]
