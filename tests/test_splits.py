from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from melanoma.data.splits import (TEST, TRAINVAL, FrozenSplitError, LeakageError, check_no_leakage,
                                  load_splits, make_splits, read_manifest, save_splits, split_hash,
                                  train_val)

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "splits" / "ham10000_v1"


def synthetic_meta(n_lesions=1500, seed=0):
    """Lesiones con 1-4 imágenes, ~10% melanoma y dos fuentes, como HAM10000 en miniatura."""
    rng = np.random.default_rng(seed)
    dx = rng.choice(["nv", "mel", "bkl", "bcc"], n_lesions, p=[0.7, 0.1, 0.12, 0.08])
    source = rng.choice(["a", "b"], n_lesions)
    reps = rng.choice([1, 2, 3, 4], n_lesions, p=[0.6, 0.25, 0.1, 0.05])
    rows = [{"lesion_id": f"L{i:05d}", "image_id": f"I{i:05d}_{r}", "dx": dx[i], "dataset": source[i]}
            for i in range(n_lesions) for r in range(reps[i])]
    meta = pd.DataFrame(rows)
    meta["label"] = (meta.dx == "mel").astype(int)
    return meta


@pytest.fixture(scope="module")
def splits():
    return make_splits(synthetic_meta(), test_fraction=0.15, n_folds=5, seed=42)


def test_no_lesion_crosses_partitions_or_folds(splits):
    per_lesion = splits.groupby("lesion_id")[["split", "fold"]].nunique()
    assert (per_lesion == 1).all().all()
    check_no_leakage(splits, n_folds=5)


def test_every_image_assigned_once(splits):
    meta = synthetic_meta()
    assert sorted(splits.image_id) == sorted(meta.image_id)
    assert set(splits.fold[splits.split == TRAINVAL]) == {0, 1, 2, 3, 4}
    assert (splits.fold[splits.split == TEST] == -1).all()


def test_sizes_and_prevalence_are_preserved(splits):
    assert (splits.split == TEST).mean() == pytest.approx(0.15, abs=0.02)
    prevalence = splits.label.mean()
    by_part = splits.groupby(["split", "fold"]).label.mean()
    assert (by_part - prevalence).abs().max() < 0.02


def test_train_val_never_includes_test(splits):
    for k in range(5):
        train, val = train_val(splits, k)
        assert not set(train.lesion_id) & set(val.lesion_id)
        assert (train.split == TRAINVAL).all() and (val.split == TRAINVAL).all()
        assert len(train) + len(val) == (splits.split == TRAINVAL).sum()


def test_same_seed_same_hash_other_seed_other_hash():
    meta = synthetic_meta()
    a, b = (make_splits(meta, 0.15, 5, seed=42) for _ in range(2))
    assert split_hash(a) == split_hash(b)
    assert split_hash(make_splits(meta, 0.15, 5, seed=7)) != split_hash(a)


def test_leakage_is_detected(splits):
    leaked = splits.copy()
    lesion = leaked.lesion_id[leaked.lesion_id.duplicated()].iloc[0]
    idx = leaked.index[leaked.lesion_id == lesion]
    leaked.loc[idx[0], ["split", "fold"]] = [TEST, -1]
    leaked.loc[idx[1], ["split", "fold"]] = [TRAINVAL, 0]
    with pytest.raises(LeakageError):
        check_no_leakage(leaked, n_folds=5)


def test_frozen_split_detects_edits_but_not_line_endings(splits, tmp_path):
    save_splits(splits, tmp_path, {"params": {"n_folds": 5, "group_column": "lesion_id"}})
    csv = tmp_path / "splits.csv"
    csv.write_bytes(csv.read_bytes().replace(b"\n", b"\r\n"))  # como tras un checkout en Windows
    assert split_hash(load_splits(tmp_path)) == split_hash(splits)

    edited = splits.copy()
    row = edited.index[edited.split == TRAINVAL][0]
    edited.loc[row, "label"] = 1 - edited.loc[row, "label"]
    edited.to_csv(csv, index=False)
    with pytest.raises(FrozenSplitError):
        load_splits(tmp_path)


@pytest.mark.skipif(not FROZEN.exists(), reason="la partición de EXP-01 aún no está congelada")
def test_frozen_ham10000_split_is_intact_and_leak_free():
    frozen = load_splits(FROZEN)  # verifica hash y fuga
    manifest = read_manifest(FROZEN)
    assert len(frozen) == manifest["source"]["images"] == 10015
    assert (frozen.split == TEST).mean() == pytest.approx(0.15, abs=0.01)
