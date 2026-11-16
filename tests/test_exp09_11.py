"""EXP-09 a EXP-11: degradación por imagen, entrenamiento con conjuntos dados, fuentes dejadas fuera,
pares unidos con EXP-06 y configuración por backbone (rápido, en CPU y sin descargar pesos)."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

tf = pytest.importorskip("tensorflow")
keras = pytest.importorskip("keras")

from melanoma.config import load_config  # noqa: E402
from melanoma.data.pipeline import make_dataset  # noqa: E402
from melanoma.data.views import random_image_degradation  # noqa: E402
from melanoma.models import backbone, build_single_view, unfreeze_backbone  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _load(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / "experiments" / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


exp09 = _load("exp09", "exp09_fuentes.py")
exp10 = _load("exp10", "exp10_una_foto_degradada.py")
exp11 = _load("exp11", "exp11_backbones.py")
DEGRADATION = {"blur_sigmas": [1.5, 3.0, 5.0], "dark_factor": [0.3, 0.7]}


def test_image_degradation_probability_zero_and_one():
    x = tf.fill((32, 40, 40, 3), 100.0)   # el desenfoque con σ = 5 refleja 15 px por lado
    same = random_image_degradation({**DEGRADATION, "probability": 0.0})(x)
    np.testing.assert_array_equal(same.numpy(), x.numpy())
    # Una imagen uniforme no cambia con desenfoque y sí con poca luz: con probabilidad 1, cerca de
    # la mitad cambia y ninguna se aclara.
    out = random_image_degradation({**DEGRADATION, "probability": 1.0})(x).numpy()
    changed = np.abs(out - 100).max(axis=(1, 2, 3)) > 1e-3
    assert 0 < changed.sum() < 32 and out.max() <= 100.0 + 1e-3


def test_degradation_only_in_training(tmp_path):
    df = pd.DataFrame({"image_id": ["ISIC_0"], "label": [0]})
    with pytest.raises(ValueError):
        make_dataset(df, tmp_path, {"image_size": 8}, 1, training=False, seed=0,
                     degradation={**DEGRADATION, "probability": 0.5})


def test_source_frames_leave_one_source_out():
    rows = []
    for i in range(40):
        rows.append({"image_id": f"ISIC_{i}", "lesion_id": f"L{i // 2}", "dataset": ["a", "b"][i % 2],
                     "split": "test" if i >= 32 else "trainval", "fold": -1 if i >= 32 else (i // 2) % 4,
                     "label": int(i % 5 == 0)})
    splits = pd.DataFrame(rows)
    train, stop, held = exp09.source_frames(splits, "a", early_stopping_fold=0)
    assert set(held.dataset) == {"a"} and set(train.dataset) == set(stop.dataset) == {"b"}
    assert (train.split == "trainval").all() and (stop.split == "trainval").all()
    assert (held.split == "trainval").all() and (stop.fold == 0).all() and (train.fold != 0).all()
    assert not set(train.image_id) & set(stop.image_id)
    assert len(held) == (splits[(splits.dataset == "a") & (splits.split == "trainval")]).shape[0]


def test_exp10_pairs_must_match_exp06():
    keys = {"lesion_id": ["L1", "L2"], "image_a": ["A1", "A2"], "image_b": ["B1", "B2"], "label": [1, 0]}
    exp06 = pd.DataFrame({**keys, "fusion": [0.9, 0.1], "average": [0.8, 0.2]})
    new = pd.DataFrame({**keys, "fold": [0, 0], "single_a": [0.7, 0.3], "single_b": [0.6, 0.2],
                        "average": [0.65, 0.25], "single_a_blur_2": [0.5, 0.3],
                        "average_blur_2": [0.55, 0.25]})
    both = exp10.merge_with_exp06(new, exp06)
    assert {"fusion", "average", "robust_average", "robust_single_a", "robust_average_blur_2",
            "robust_single_a_blur_2"} <= set(both.columns)
    assert both.robust_average.tolist() == [0.65, 0.25] and both.average.tolist() == [0.8, 0.2]
    with pytest.raises(SystemExit):
        exp10.merge_with_exp06(new.assign(image_b=["B1", "otra"]), exp06)


def test_exp10_config_is_exp03_plus_degradation():
    cfg = load_config(ROOT / "configs" / "exp10_una_foto_degradada.yaml")
    base = load_config(ROOT / "configs" / "base.yaml")
    exp06 = load_config(ROOT / "configs" / "exp06_dos_fotos.yaml")
    assert cfg["training"]["phases"] == base["training"]["phases"]
    assert cfg["training"]["imbalance"] == "none" and cfg["seed"] == 42
    deg = cfg["training"]["image_degradation"]
    assert deg["blur_sigmas"] == exp06["view_degradation"]["blur_sigmas"]
    assert deg["dark_factor"] == exp06["view_degradation"]["dark_factor"]
    assert deg["probability"] == exp06["view_degradation"]["probability"] / 2
    assert cfg["evaluation_degradations"] == exp06["evaluation_degradations"]


def test_exp11_backbone_config():
    cfg = load_config(ROOT / "configs" / "exp11_backbones.yaml")
    cfg["backbones"]["efficientnet_v2_s"] = {"training": {"batch_size": 16}}
    b0 = exp11.backbone_config(cfg, "efficientnet_v2_b0")
    s = exp11.backbone_config(cfg, "efficientnet_v2_s")
    assert b0["model"]["backbone"] == "efficientnet_v2_b0" and b0["training"]["batch_size"] == 32
    assert s["model"]["backbone"] == "efficientnet_v2_s" and s["training"]["batch_size"] == 16
    assert s["training"]["phases"] == b0["training"]["phases"]
    assert not set(exp11.EXPERIMENT_KEYS) & set(b0)


def test_efficientnet_single_view_builds_and_freezes_batchnorm():
    keras.mixed_precision.set_global_policy("float32")
    model = build_single_view({"backbone": "efficientnet_v2_b0", "weights": None, "dropout": 0.2}, 64)
    out = model(np.zeros((2, 64, 64, 3), "float32"))
    assert out.shape == (2, 1) and out.dtype == "float32"
    unfreeze_backbone(model)
    bns = [la for la in backbone(model).layers if isinstance(la, keras.layers.BatchNormalization)]
    assert bns and not any(la.trainable for la in bns)
