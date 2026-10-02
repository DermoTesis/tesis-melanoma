"""Pipeline de imágenes, modelo y entrenamiento en dos fases, con imágenes sintéticas y sin
descargar pesos (rápido, en CPU)."""

import numpy as np
import pandas as pd
import pytest

tf = pytest.importorskip("tensorflow")
keras = pytest.importorskip("keras")

from melanoma.data.pipeline import limit_images, make_dataset  # noqa: E402
from melanoma.models import backbone, build_single_view  # noqa: E402
from melanoma.training import train_fold_isolated, train_two_phases  # noqa: E402

SIZE = 64
DATA_CFG = {"image_size": SIZE, "cache": True,
            "augmentation": {"flip": True, "rotation": 0.5, "zoom": 0.2, "brightness": 0.1,
                             "contrast": 0.1}}
MODEL_CFG = {"backbone": "mobilenet_v3_large", "weights": None, "dropout": 0.2}
PHASES = {"phases": {"head": {"epochs": 1, "learning_rate": 1e-3},
                     "finetune": {"epochs": 2, "learning_rate": 1e-3}},
          "early_stopping_patience": 5}


@pytest.fixture()
def images(tmp_path):
    """12 JPEG de 60×45 (como HAM10000, 4:3): los positivos son más oscuros."""
    rng = np.random.default_rng(0)
    rows = []
    for i in range(12):
        label = i % 3 == 0
        pixels = rng.integers(0, 120 if label else 255, (45, 60, 3), dtype=np.uint8)
        tf.io.write_file(str(tmp_path / f"ISIC_{i:07d}.jpg"), tf.io.encode_jpeg(pixels))
        rows.append({"image_id": f"ISIC_{i:07d}", "lesion_id": f"HAM_{i // 2:07d}",
                     "dx": "mel" if label else "nv", "label": int(label)})
    return tmp_path, pd.DataFrame(rows)


def test_eval_dataset_keeps_order_size_and_pixel_range(images):
    images_dir, df = images
    batches = list(make_dataset(df, images_dir, DATA_CFG, 5, training=False, seed=0))
    x = np.concatenate([b[0].numpy() for b in batches])
    y = np.concatenate([b[1].numpy() for b in batches])
    assert x.shape == (12, SIZE, SIZE, 3) and x.dtype == np.float32
    assert 0 <= x.min() and x.max() <= 255
    np.testing.assert_array_equal(y, df.label.to_numpy())
    again = np.concatenate([b[0].numpy() for b in make_dataset(df, images_dir, DATA_CFG, 5,
                                                                 training=False, seed=0)])
    np.testing.assert_array_equal(x, again)


def test_training_dataset_augments_differently_each_epoch(images):
    images_dir, df = images
    ds = make_dataset(df.head(1), images_dir, DATA_CFG, 1, training=True, seed=0)
    first, second = (next(iter(ds))[0].numpy() for _ in range(2))
    assert np.abs(first - second).mean() > 1.0


def test_limit_images_keeps_both_classes():
    df = pd.DataFrame({"image_id": [f"i{k:03d}" for k in range(100)],
                       "label": [1] * 10 + [0] * 90})
    small = limit_images(df, 20, seed=0)
    assert len(small) == 20 and small.label.sum() == 2
    assert limit_images(df, None, seed=0) is df


def test_model_outputs_float32_probability_and_has_one_backbone():
    keras.mixed_precision.set_global_policy("float32")
    model = build_single_view(MODEL_CFG, SIZE)
    out = model(np.zeros((2, SIZE, SIZE, 3), dtype="float32"))
    assert out.shape == (2, 1) and out.dtype == "float32"
    assert isinstance(backbone(model), keras.Model)


def test_two_phase_training_freezes_then_unfreezes_backbone(images, tmp_path):
    images_dir, df = images
    keras.mixed_precision.set_global_policy("float32")
    model = build_single_view(MODEL_CFG, SIZE)
    base = backbone(model)
    before = [w.numpy().copy() for w in base.trainable_weights[:3]]
    batchnorms = [la for la in base.layers if isinstance(la, keras.layers.BatchNormalization)]
    stats = [w.numpy().copy() for la in batchnorms for w in (la.moving_mean, la.moving_variance)]
    ds = make_dataset(df, images_dir, DATA_CFG, 4, training=True, seed=0)
    val = make_dataset(df, images_dir, DATA_CFG, 4, training=False, seed=0)
    info = train_two_phases(model, ds, val, PHASES, tmp_path / "fold", verbose=0)
    assert base.trainable
    assert info["head_epochs"] == 1 and info["finetune_epochs"] == 2
    assert 2 <= info["best_epoch"] <= 3
    assert len(info["history"]["val_auc"]) == 3
    assert (tmp_path / "fold" / "historial.csv").exists()
    after = [w.numpy() for w in base.trainable_weights[:3]]
    assert any(not np.allclose(a, b) for a, b in zip(before, after))
    # Las BatchNorm siguen en modo inferencia: ni se entrenan ni cambian sus estadísticas.
    assert batchnorms and not any(la.trainable for la in batchnorms)
    now = [w.numpy() for la in batchnorms for w in (la.moving_mean, la.moving_variance)]
    assert all(np.array_equal(a, b) for a, b in zip(stats, now))


def test_fold_in_separate_process_returns_predictions_and_saves_model(images, tmp_path):
    images_dir, df = images
    splits = df.assign(split="trainval", fold=[i % 2 for i in range(len(df))])
    cfg = {"seed": 0, "model": MODEL_CFG, "data": {**DATA_CFG, "max_images": None},
           "training": {**PHASES, "batch_size": 4, "mixed_precision": True,
                        "jit_compile": True}}
    pred, info = train_fold_isolated(cfg, splits, 1, images_dir, tmp_path / "fold_1", verbose=0)
    assert list(pred.image_id) == list(splits[splits.fold == 1].image_id)
    assert pred.prob.between(0, 1).all() and (pred.fold == 1).all()
    assert info["n_train_images"] == 6
    assert (tmp_path / "fold_1" / "modelo.keras").exists()
