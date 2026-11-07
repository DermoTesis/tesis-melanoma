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


def test_focal_alpha_turns_on_class_balancing():
    plain = setup({**TRAINING, "imbalance": "focal_loss"}, np.array([1, 0]))["loss"].get_config()
    assert plain["apply_class_balancing"] is False
    alpha = setup({**TRAINING, "imbalance": "focal_loss", "focal_alpha": 0.25},
                  np.array([1, 0]))["loss"].get_config()
    assert alpha["apply_class_balancing"] is True and alpha["alpha"] == 0.25 and alpha["gamma"] == 2.0


def test_asymmetric_loss_strategy_uses_its_parameters():
    from melanoma.losses import AsymmetricLoss

    loss = setup({"imbalance": "asymmetric_loss", "asl_gamma_neg": 3.0, "asl_clip": 0.1},
                 np.array([1, 0]))["loss"]
    assert isinstance(loss, AsymmetricLoss)
    assert (loss.gamma_pos, loss.gamma_neg, loss.clip) == (0.0, 3.0, 0.1)
    default = setup({"imbalance": "asymmetric_loss"}, np.array([1, 0]))["loss"]
    assert (default.gamma_pos, default.gamma_neg, default.clip) == (0.0, 4.0, 0.05)


def test_two_view_and_final_models_only_accept_loss_strategies():
    from melanoma.imbalance import loss_only

    assert loss_only({"imbalance": "none"}) == "binary_crossentropy"
    assert loss_only({}) == "binary_crossentropy"
    assert isinstance(loss_only({**TRAINING, "imbalance": "focal_loss"}),
                      keras.losses.BinaryFocalCrossentropy)
    for strategy in ("class_weight", "oversampling"):
        with pytest.raises(ValueError, match="no está implementada"):
            loss_only({**TRAINING, "imbalance": strategy})
