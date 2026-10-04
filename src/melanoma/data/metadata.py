"""Datos del paciente de HAM10000 (EXP-07): edad, sexo y zona del cuerpo.

Son los mismos que registra la app: la fecha de nacimiento y el sexo del paciente (HU06) y la
ubicación de la lesión (HU11). La app tiene que usar estas 15 zonas, o una correspondencia con
ellas. Los datos que falten se codifican como desconocidos, igual que en HAM10000.

Vector de 20 valores: edad / 100, indicador de edad faltante, sexo (3) y zona (15), estas dos en
one-hot.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SEXES = ("male", "female", "unknown")
LOCALIZATIONS = ("abdomen", "acral", "back", "chest", "ear", "face", "foot", "genital", "hand",
                 "lower extremity", "neck", "scalp", "trunk", "unknown", "upper extremity")
N_FEATURES = 2 + len(SEXES) + len(LOCALIZATIONS)


def load(metadata_csv: str | Path) -> pd.DataFrame:
    """Edad, sexo y zona por imagen, indexados por `image_id`."""
    return pd.read_csv(metadata_csv).set_index("image_id")[["age", "sex", "localization"]]


def encode(df: pd.DataFrame) -> np.ndarray:
    """float32 (n, N_FEATURES) a partir de las columnas `age`, `sex` y `localization`."""
    age = pd.to_numeric(df["age"], errors="coerce")
    missing = age.isna().to_numpy()
    sex = df["sex"].where(df["sex"].isin(SEXES), "unknown").to_numpy()
    zone = df["localization"].where(df["localization"].isin(LOCALIZATIONS), "unknown").to_numpy()
    columns = [np.where(missing, 0.0, age.fillna(0).to_numpy() / 100), missing.astype(float),
               *[(sex == s).astype(float) for s in SEXES],
               *[(zone == z).astype(float) for z in LOCALIZATIONS]]
    return np.column_stack(columns).astype(np.float32)


def for_images(image_ids, table: pd.DataFrame) -> np.ndarray:
    """Vectores de las imágenes pedidas (en una lesión se usa el de su foto A)."""
    return encode(table.loc[list(image_ids)])
