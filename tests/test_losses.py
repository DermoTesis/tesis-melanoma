"""Pérdida asimétrica (ASL) de EXP-08."""

import numpy as np
import pytest

tf = pytest.importorskip("tensorflow")
keras = pytest.importorskip("keras")

from melanoma.losses import AsymmetricLoss  # noqa: E402


def per_example(loss, y, p):
    return np.asarray(loss.call(tf.constant(y, tf.float32), tf.constant(p, tf.float32)))


def test_without_focusing_or_margin_it_is_binary_cross_entropy():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 64).astype("float32")
    p = rng.uniform(0.01, 0.99, (64, 1)).astype("float32")
    asl = AsymmetricLoss(gamma_pos=0, gamma_neg=0, clip=0)
    bce = keras.losses.BinaryCrossentropy()
    assert float(asl(y, p)) == pytest.approx(float(bce(y[:, None], p)), rel=1e-5)


def test_positive_term_is_cross_entropy_when_gamma_pos_is_zero():
    out = per_example(AsymmetricLoss(), [1.0, 1.0], [[0.2], [0.9]])
    assert out.ravel() == pytest.approx(-np.log([0.2, 0.9]), rel=1e-5)


def test_margin_discards_easy_negatives_with_no_gradient():
    loss = AsymmetricLoss(gamma_neg=4, clip=0.05)
    p = tf.Variable([[0.03], [0.5]])
    with tf.GradientTape() as tape:
        out = loss.call(tf.constant([0.0, 0.0]), p)
        total = tf.reduce_sum(out)
    grad = tape.gradient(total, p).numpy().ravel()
    assert out.numpy()[0, 0] == 0 and grad[0] == 0       # p < m: no cuenta
    assert out.numpy()[1, 0] > 0 and grad[1] > 0         # benigno dudoso: empuja p hacia abajo


def test_focusing_concentrates_on_hard_negatives():
    p = [[0.1], [0.8]]                                  # benigno fácil y benigno que parece melanoma
    asl = per_example(AsymmetricLoss(gamma_neg=4, clip=0.05), [0.0, 0.0], p).ravel()
    bce = per_example(AsymmetricLoss(gamma_neg=0, clip=0), [0.0, 0.0], p).ravel()
    assert asl[1] / asl[0] > 100 * (bce[1] / bce[0])


def test_focusing_weight_is_treated_as_a_constant():
    # Como el entrenamiento oficial: d/dp[-w · log(1 − p_m)] = w / (1 − p_m), con w fijo.
    p_value, m, gamma = 0.6, 0.05, 4.0
    p = tf.Variable([[p_value]])
    with tf.GradientTape() as tape:
        out = AsymmetricLoss(gamma_neg=gamma, clip=m).call(tf.constant([0.0]), p)
    p_m = p_value - m
    expected = p_m ** gamma / (1 - p_m)
    assert tape.gradient(out, p).numpy().item() == pytest.approx(expected, rel=1e-4)


def test_invalid_parameters_are_rejected():
    with pytest.raises(ValueError):
        AsymmetricLoss(gamma_neg=-1)
    with pytest.raises(ValueError):
        AsymmetricLoss(clip=1.0)


def test_model_with_the_loss_can_be_saved_and_loaded(tmp_path):
    inputs = keras.Input((3,))
    model = keras.Model(inputs, keras.layers.Dense(1, activation="sigmoid")(inputs))
    model.compile(optimizer="adam", loss=AsymmetricLoss(gamma_neg=3.0, clip=0.1))
    x = np.random.default_rng(0).normal(size=(16, 3)).astype("float32")
    y = (x[:, 0] > 0).astype("float32")
    model.fit(x, y, epochs=1, verbose=0)
    model.save(tmp_path / "modelo.keras")
    loaded = keras.models.load_model(tmp_path / "modelo.keras")
    assert np.allclose(loaded.predict(x, verbose=0), model.predict(x, verbose=0))
    config = AsymmetricLoss.from_config(AsymmetricLoss(gamma_neg=3.0, clip=0.1).get_config())
    assert (config.gamma_neg, config.clip, config.stop_gradient_weights) == (3.0, 0.1, True)
