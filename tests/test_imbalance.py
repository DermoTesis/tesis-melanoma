"""Estrategias de desbalance de EXP-03."""

import numpy as np
import pandas as pd
import pytest

tf = pytest.importorskip("tensorflow")
keras = pytest.importorskip("keras")

from melanoma.data.pipeline import make_dataset  # noqa: E402
from melanoma.imbalance import class_weights, setup  # noqa: E402

TRAINING = {"oversampling_positive_fraction": 0.5, "focal_gamma": 2.0}


def test_balanced_class_weights_make_both_classes_weigh_the_same():
    labels = np.array([1] * 10 + [0] * 90)
    w = class_weights(labels)
    assert w[1] == pytest.approx(5.0) and w[0] == pytest.approx(100 / 180)
    assert 10 * w[1] == pytest.approx(90 * w[0])
    with pytest.raises(ValueError):
        class_weights(np.zeros(5))


def test_setup_translates_each_strategy():
    labels = np.array([1, 0, 0, 0])
    assert setup({**TRAINING, "imbalance": "none"}, labels) == {
        "loss": "binary_crossentropy", "class_weight": None, "positive_fraction": None}
    assert setup({**TRAINING, "imbalance": "class_weight"}, labels)["class_weight"][1] == 2.0
    assert setup({**TRAINING, "imbalance": "oversampling"}, labels)["positive_fraction"] == 0.5
    focal = setup({**TRAINING, "imbalance": "focal_loss"}, labels)["loss"]
    assert isinstance(focal, keras.losses.BinaryFocalCrossentropy)
    with pytest.raises(ValueError):
        setup({**TRAINING, "imbalance": "smote"}, labels)


def test_oversampling_balances_training_batches_only(tmp_path):
    rows = []
    for i in range(40):
        tf.io.write_file(str(tmp_path / f"ISIC_{i:07d}.jpg"),
                         tf.io.encode_jpeg(np.full((45, 60, 3), i, dtype=np.uint8)))
        rows.append({"image_id": f"ISIC_{i:07d}", "label": int(i < 4)})
    df = pd.DataFrame(rows)
    cfg = {"image_size": 32, "cache": True, "augmentation": {}}
    ds = make_dataset(df, tmp_path, cfg, 8, training=True, seed=0, positive_fraction=0.5)
    labels = np.concatenate([y.numpy() for _, y in ds.take(50)])
    assert labels.mean() == pytest.approx(0.5, abs=0.06)   # sin sobremuestreo sería 0.1
    with pytest.raises(ValueError):
        make_dataset(df, tmp_path, cfg, 8, training=False, seed=0, positive_fraction=0.5)
