"""Partición sin fuga por lesión (EXP-01): un test fijo y k folds, congelados con hash.

Todas las imágenes de una misma lesión quedan en la misma partición y en el mismo fold, y los
estratos (por defecto, clase × fuente de HAM10000) mantienen sus proporciones en cada partición.

La partición se guarda en `splits/<nombre>/` como `splits.csv` y `manifest.json`. El hash se
calcula sobre el contenido normalizado del CSV, no sobre los bytes, para que git en Windows (que
puede cambiar los saltos de línea) no lo invalide. `load_splits` recalcula el hash y revisa que
no haya fuga antes de devolver nada.
"""

from __future__ import annotations

import hashlib
import io
import json
import warnings
from fractions import Fraction
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold

TEST, TRAINVAL = "test", "trainval"
COLUMNS = ["image_id", "lesion_id", "dx", "label", "dataset", "split", "fold"]
CSV_NAME, MANIFEST_NAME = "splits.csv", "manifest.json"


class LeakageError(AssertionError):
    """Una lesión aparece en más de una partición o fold, o una imagen está mal asignada."""


class FrozenSplitError(RuntimeError):
    """La partición congelada no coincide con su hash o con la que se regenera."""


def make_splits(meta: pd.DataFrame, test_fraction: float, n_folds: int, seed: int,
                group_column: str = "lesion_id",
                stratify_by: Sequence[str] = ("dx", "dataset")) -> pd.DataFrame:
    """Asigna cada imagen a `test` o a `trainval`, y dentro de `trainval` a un fold 0..k-1.

    El test se arma con StratifiedGroupKFold: la fracción se aproxima con denominador ≤ 20
    (0.15 = 3/20) y se toman esos folds. El resto se reparte en `n_folds` con el mismo método.
    """
    strata = meta[list(stratify_by)].astype(str).agg("|".join, axis=1).to_numpy()
    groups = meta[group_column].to_numpy()

    frac = Fraction(test_fraction).limit_denominator(20)
    outer = StratifiedGroupKFold(n_splits=frac.denominator, shuffle=True, random_state=seed)
    inner = StratifiedGroupKFold(n_splits=n_folds, shuffle=True, random_state=seed)
    with warnings.catch_warnings():
        # Algunos estratos clase × fuente tienen menos imágenes que folds; es esperable.
        warnings.filterwarnings("ignore", message="The least populated class in y")
        parts = [held for _, held in outer.split(np.zeros(len(meta)), strata, groups)]
        is_test = np.zeros(len(meta), dtype=bool)
        is_test[np.concatenate(parts[:frac.numerator])] = True

        fold = np.full(len(meta), -1)
        trainval = np.flatnonzero(~is_test)
        for k, (_, held) in enumerate(inner.split(trainval, strata[trainval], groups[trainval])):
            fold[trainval[held]] = k

    splits = meta.assign(split=np.where(is_test, TEST, TRAINVAL), fold=fold)[COLUMNS]
    splits = splits.sort_values("image_id").reset_index(drop=True)
    check_no_leakage(splits, n_folds, group_column)
    return splits


def check_no_leakage(splits: pd.DataFrame, n_folds: int, group_column: str = "lesion_id") -> None:
    """Falla si una lesión cruza particiones o folds, o si hay imágenes mal asignadas."""
    if splits.image_id.duplicated().any():
        raise LeakageError("Hay imágenes asignadas más de una vez")
    if not splits.split.isin([TEST, TRAINVAL]).all():
        raise LeakageError(f"Particiones desconocidas: {sorted(set(splits.split) - {TEST, TRAINVAL})}")
    test = splits.split == TEST
    if (splits.fold[test] != -1).any():
        raise LeakageError("Imágenes de test con fold asignado")
    if not splits.fold[~test].between(0, n_folds - 1).all():
        raise LeakageError(f"Imágenes de trainval sin fold válido (0..{n_folds - 1})")
    crossing = splits.groupby(group_column)[["split", "fold"]].nunique().max(axis=1) > 1
    if crossing.any():
        raise LeakageError(f"{int(crossing.sum())} lesiones en más de una partición o fold, "
                           f"p. ej. {crossing[crossing].index.tolist()[:5]}")


def train_val(splits: pd.DataFrame, fold: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(entrenamiento, validación) del fold `fold`; el test nunca entra."""
    trainval = splits[splits.split == TRAINVAL]
    return trainval[trainval.fold != fold], trainval[trainval.fold == fold]


def split_hash(splits: pd.DataFrame) -> str:
    return hashlib.sha256(_canonical_csv(splits).encode("utf-8")).hexdigest()


def save_splits(splits: pd.DataFrame, out_dir: str | Path, manifest: dict[str, Any]) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / CSV_NAME).write_text(_canonical_csv(splits), encoding="utf-8")
    payload = {"sha256": split_hash(splits), **manifest}
    (out_dir / MANIFEST_NAME).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                                         encoding="utf-8")
    return out_dir


def load_splits(split_dir: str | Path) -> pd.DataFrame:
    """Lee una partición congelada verificando su hash y que no tenga fuga."""
    split_dir = Path(split_dir)
    manifest = read_manifest(split_dir)
    splits = pd.read_csv(split_dir / CSV_NAME, dtype={"split": str, "fold": int, "label": int})
    actual = split_hash(splits)
    if actual != manifest["sha256"]:
        raise FrozenSplitError(f"{split_dir / CSV_NAME} fue modificado: hash {actual[:12]}…, "
                               f"el manifiesto dice {manifest['sha256'][:12]}…")
    check_no_leakage(splits, manifest["params"]["n_folds"], manifest["params"]["group_column"])
    return splits


def read_manifest(split_dir: str | Path) -> dict[str, Any]:
    return json.loads((Path(split_dir) / MANIFEST_NAME).read_text(encoding="utf-8"))


def summarize(splits: pd.DataFrame) -> pd.DataFrame:
    """Una fila por partición (test y cada fold): imágenes, lesiones y prevalencia del positivo."""
    df = splits.assign(part=np.where(splits.split == TEST, TEST, "fold_" + splits.fold.astype(str)))
    grouped = df.groupby("part")
    table = pd.DataFrame({
        "images": grouped.size(),
        "lesions": grouped.lesion_id.nunique(),
        "positive_images": grouped.label.sum(),
        "positive_lesions": df[df.label == 1].groupby("part").lesion_id.nunique(),
    }).fillna(0).astype(int)
    table["prevalence"] = (table.positive_images / table.images).round(4)
    table["fraction"] = (table.images / len(splits)).round(4)
    return table.reset_index()


def _canonical_csv(splits: pd.DataFrame) -> str:
    canonical = splits[COLUMNS].sort_values("image_id").reset_index(drop=True)
    buffer = io.StringIO()
    canonical.to_csv(buffer, index=False, lineterminator="\n")
    return buffer.getvalue()
