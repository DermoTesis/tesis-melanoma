"""EXP-01: partición sin fuga de datos por lesión (test fijo + 5 folds), congelada en splits/.

    python experiments/exp01_particion.py

La primera vez crea `splits/<split.name>/`. Las siguientes, regenera la partición y comprueba que
salga idéntica a la congelada (mismo hash); si difiere, se detiene sin sobrescribir nada. Para una
partición nueva hay que cambiar `split.name`.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from importlib import metadata

import numpy as np
import pandas as pd

from melanoma.config import parse_cli
from melanoma.data import ham10000
from melanoma.data.splits import (TEST, FrozenSplitError, load_splits, make_splits, save_splits,
                                  split_hash, summarize)
from melanoma.runs import PROJECT_ROOT, start_run

CONFIG = PROJECT_ROOT / "configs" / "exp01_particion.yaml"


def main(argv: list[str] | None = None) -> int:
    cfg, _ = parse_cli(__doc__.splitlines()[0], CONFIG, argv)
    source = cfg["data"]["sources"]["ham10000"]
    split_cfg = cfg["split"]

    meta = ham10000.load_metadata(PROJECT_ROOT / source["metadata"], cfg["data"]["positive_classes"],
                                  expected_md5=source["metadata_md5"])
    splits = make_splits(meta, split_cfg["test_fraction"], split_cfg["n_folds"], cfg["seed"],
                         split_cfg["group_column"], split_cfg["stratify_by"])
    digest = split_hash(splits)

    split_dir = PROJECT_ROOT / cfg["paths"]["splits"] / split_cfg["name"]
    if (split_dir / "manifest.json").exists():
        frozen_digest = split_hash(load_splits(split_dir))
        if frozen_digest != digest:
            raise FrozenSplitError(
                f"La partición regenerada ({digest[:12]}…) no coincide con la congelada en "
                f"{split_dir} ({frozen_digest[:12]}…). No se sobrescribe; para una partición "
                "nueva, cambiar split.name.")
        print(f"Partición congelada verificada: se reproduce idéntica (sha256 {digest[:12]}…).")
    else:
        save_splits(splits, split_dir, manifest={
            "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "params": {**split_cfg, "seed": cfg["seed"],
                       "positive_classes": cfg["data"]["positive_classes"]},
            "source": {"metadata": source["metadata"], "metadata_md5": source["metadata_md5"],
                       "images": int(len(meta)), "lesions": int(meta.lesion_id.nunique())},
            "versions": {p: metadata.version(p) for p in ("scikit-learn", "pandas", "numpy")},
        })
        print(f"Partición creada y congelada en {split_dir.relative_to(PROJECT_ROOT)} "
              f"(sha256 {digest[:12]}…).")

    table = summarize(splits)
    print("\n" + table.to_string(index=False))

    part = np.where(splits.split == TEST, TEST, "fold_" + splits.fold.astype(str))
    by_dx = pd.crosstab(part, splits.dx, rownames=["part"])
    by_source = pd.crosstab(part, splits.dataset, rownames=["part"])
    print("\nImágenes por clase:\n" + by_dx.to_string())
    print("\nImágenes por fuente:\n" + by_source.to_string())

    images_dir = PROJECT_ROOT / source["images"]
    missing = ham10000.missing_images(meta, images_dir) if images_dir.is_dir() else None
    if missing is None:
        print(f"\nAviso: no existe {source['images']}; no se comprobó que estén las imágenes.")
    elif missing:
        print(f"\nAviso: faltan {len(missing)} imágenes en {source['images']}, p. ej. {missing[:3]}")
    else:
        print(f"\nLas {len(meta)} imágenes están en {source['images']}.")

    run = start_run(cfg, "exp01", split_cfg["name"])
    run.save_metrics(
        rows=[{"split_name": split_cfg["name"], **row} for row in table.to_dict("records")],
        details={"sha256": digest, "by_dx": _as_dict(by_dx), "by_source": _as_dict(by_source),
                 "missing_images": missing})
    print(f"Corrida registrada en {run.results_dir.relative_to(PROJECT_ROOT)}")
    return 0


def _as_dict(table: pd.DataFrame) -> dict:
    return {str(row): {str(col): int(v) for col, v in values.items()}
            for row, values in table.to_dict("index").items()}


if __name__ == "__main__":
    sys.exit(main())
