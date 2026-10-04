"""EXP-06: modelo de dos fotos, pares de una misma lesión y degradación de una vista."""

import numpy as np
import pandas as pd
import pytest

tf = pytest.importorskip("tensorflow")
keras = pytest.importorskip("keras")

from melanoma.data.views import (degrade, fixed_pairs, load_images, random_view_degradation,  # noqa: E402
                                 training_pairs)
from melanoma.models import build_single_view, build_two_view, view_weights  # noqa: E402
from melanoma.multiview import two_view_fold  # noqa: E402

SIZE = 64
MODEL_CFG = {"backbone": "mobilenet_v3_large", "weights": None, "dropout": 0.2}


@pytest.fixture()
def single():
    keras.mixed_precision.set_global_policy("float32")
    return build_single_view(MODEL_CFG, SIZE)


def test_two_view_is_symmetric_and_equals_single_view_with_the_same_photo(single):
    rng = np.random.default_rng(0)
    a, b = (rng.uniform(0, 255, (3, SIZE, SIZE, 3)).astype("float32") for _ in range(2))
    expected = single.predict(a, verbose=0).ravel()
    model = build_two_view(single, {"hidden": 8})
    same = model.predict({"view_a": a, "view_b": a}, verbose=0).ravel()
    np.testing.assert_allclose(same, expected, atol=1e-6)
    ab = model.predict({"view_a": a, "view_b": b}, verbose=0).ravel()
    ba = model.predict({"view_a": b, "view_b": a}, verbose=0).ravel()
    np.testing.assert_allclose(ab, ba, atol=1e-6)
    w = view_weights(model).predict({"view_a": a, "view_b": b}, verbose=0)
    np.testing.assert_allclose(w.sum(axis=1), 1, atol=1e-6)


def lesions_df():
    rows = []
    for lesion, n in enumerate([1, 2, 3, 2, 1]):
        for k in range(n):
            rows.append({"image_id": f"ISIC_{lesion}{k}", "lesion_id": f"HAM_{lesion}",
                         "label": int(lesion == 2), "dx": "mel" if lesion == 2 else "nv",
                         "dataset": "x"})
    return pd.DataFrame(rows)


def test_fixed_pairs_use_two_different_photos_of_each_multi_photo_lesion():
    df = lesions_df()
    pairs = fixed_pairs(df, seed=0)
    assert list(pairs.lesion_id) == ["HAM_1", "HAM_2", "HAM_3"]
    assert (pairs.image_a != pairs.image_b).all()
    for p in pairs.itertuples():
        assert p.image_a[:-1] == p.image_b[:-1] == "ISIC_" + p.lesion_id[-1]
    pd.testing.assert_frame_equal(pairs, fixed_pairs(df, seed=0))
    assert pairs.set_index("lesion_id").label.to_dict() == {"HAM_1": 0, "HAM_2": 1, "HAM_3": 0}


def test_degradations_blur_and_darken():
    rng = np.random.default_rng(0)
    images = rng.uniform(0, 255, (2, SIZE, SIZE, 3)).astype("float32")
    blurred = degrade(images, "blur", 3.0).numpy()
    assert blurred.shape == images.shape
    assert blurred.std() < images.std() / 2 and abs(blurred.mean() - images.mean()) < 2
    np.testing.assert_allclose(degrade(images, "dark", 0.5).numpy(), images * 0.5, rtol=1e-6)
    with pytest.raises(ValueError):
        degrade(images, "noise", 1.0)


def test_random_degradation_touches_at_most_one_view():
    a = tf.fill((64, 8, 8, 3), 100.0)
    b = tf.fill((64, 8, 8, 3), 200.0)
    cfg = {"probability": 1.0, "blur_sigmas": [1.0], "dark_factor": [0.5, 0.5]}
    a2, b2 = random_view_degradation(cfg)(a, b)
    changed_a = np.abs(a2.numpy() - 100).max(axis=(1, 2, 3)) > 1e-3
    changed_b = np.abs(b2.numpy() - 200).max(axis=(1, 2, 3)) > 1e-3
    # Con desenfoque de una imagen uniforme no cambia nada; con poca luz sí. Nunca las dos.
    assert not np.any(changed_a & changed_b) and np.any(changed_a | changed_b)


def test_training_pairs_come_from_the_same_lesion():
    # El valor del píxel codifica lesión (decenas) y foto (unidades).
    values = [10, 11, 12, 20, 21, 30, 31]
    images = np.stack([np.full((SIZE, SIZE, 3), v, np.uint8) for v in values])
    groups = [np.array([0, 1, 2]), np.array([3, 4]), np.array([5, 6])]
    ds = training_pairs(images, groups, np.array([0, 1, 0]), {"augmentation": {}}, None,
                        batch_size=4, seed=0)
    for x, y in ds.take(5):
        a = x["view_a"].numpy()[:, 0, 0, 0]
        b = x["view_b"].numpy()[:, 0, 0, 0]
        assert np.all(a // 10 == b // 10) and np.all(a != b)
        np.testing.assert_array_equal(y.numpy(), (a // 10 == 2).astype("float32"))


def test_two_view_fold_end_to_end(tmp_path, single):
    rng = np.random.default_rng(0)
    df = lesions_df()
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    for image_id in df.image_id:
        pixels = rng.integers(0, 255, (45, 60, 3), dtype=np.uint8)
        tf.io.write_file(str(images_dir / f"{image_id}.jpg"), tf.io.encode_jpeg(pixels))
    # Dos copias de las lesiones para tener entrenamiento y validación con 2 o más fotos.
    other = df.assign(image_id=df.image_id + "b", lesion_id=df.lesion_id + "b")
    for image_id in other.image_id:
        tf.io.write_file(str(images_dir / f"{image_id}.jpg"),
                         tf.io.encode_jpeg(rng.integers(0, 255, (45, 60, 3), dtype=np.uint8)))
    splits = pd.concat([df.assign(fold=0), other.assign(fold=1)]).assign(split="trainval")
    single.save(tmp_path / "single.keras")
    cfg = {"seed": 0, "model": MODEL_CFG, "pairs": {"max_lesions": None},
           "data": {"image_size": SIZE, "augmentation": {"flip": True}},
           "fusion": {"hidden": 8, "dropout": 0.0},
           "view_degradation": {"probability": 0.5, "blur_sigmas": [1.0], "dark_factor": [0.3, 0.7]},
           "evaluation_degradations": {"blur": [2.0], "dark": [0.5]},
           "training": {"batch_size": 2, "early_stopping_patience": 2,
                        "phases": {"head": {"epochs": 1, "learning_rate": 1e-3},
                                   "finetune": {"epochs": 1, "learning_rate": 1e-4}}}}
    pred, info = two_view_fold(cfg, splits, 0, images_dir, tmp_path / "single.keras",
                               tmp_path / "fold_0", verbose=0)
    assert list(pred.lesion_id) == ["HAM_1", "HAM_2", "HAM_3"]
    for col in ("single_a", "single_b", "average", "fusion", "fusion_single", "weight_a",
                "single_a_blur_2", "average_dark_0.5", "fusion_blur_2", "weight_a_dark_0.5"):
        assert pred[col].between(0, 1).all(), col
    np.testing.assert_allclose(pred.average, (pred.single_a + pred.single_b) / 2)
    assert info["n_train_lesions"] == 3 and (tmp_path / "fold_0" / "modelo.keras").exists()
    images = load_images(["ISIC_10", "ISIC_11"], images_dir, SIZE)
    assert images.shape == (2, SIZE, SIZE, 3) and images.dtype == np.uint8


def test_final_models_train_on_all_trainval_without_validation(tmp_path, single):
    from melanoma.final_model import train_final
    rng = np.random.default_rng(1)
    df = lesions_df()
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    for image_id in df.image_id:
        tf.io.write_file(str(images_dir / f"{image_id}.jpg"),
                         tf.io.encode_jpeg(rng.integers(0, 255, (45, 60, 3), dtype=np.uint8)))
    test_row = df.iloc[[0]].assign(split="test", fold=-1)
    splits = pd.concat([df.iloc[1:].assign(split="trainval", fold=0), test_row])
    phases = {"head": {"epochs": 1, "learning_rate": 1e-3}, "finetune": {"epochs": 1, "learning_rate": 1e-4}}
    cfg = {"seed": 0, "model": MODEL_CFG, "fusion": {"hidden": 8},
           "data": {"image_size": SIZE, "cache": True, "augmentation": {}, "max_images": None},
           "view_degradation": None,
           "training": {"batch_size": 2, "early_stopping_patience": 2, "imbalance": "none"},
           "final": {"single_view": {"phases": phases}, "two_view": {"phases": phases}}}
    info = train_final(cfg, splits, images_dir, tmp_path / "final", verbose=0)
    assert (tmp_path / "final" / "una_foto.keras").exists()
    assert (tmp_path / "final" / "dos_fotos.keras").exists()
    assert info["single_view"]["n_train_images"] == len(df) - 1   # el test no entra
    assert info["two_view"]["n_train_lesions"] == 3
    assert info["two_view"]["best_epoch"] == 2 and "best_val_auc_keras" not in info["two_view"]


def test_patient_data_encoding_and_metadata_model_start_like_the_fusion(single):
    from melanoma.data import metadata as patient
    from melanoma.models import with_metadata
    df = pd.DataFrame({"age": [45.0, None], "sex": ["female", "weird"],
                       "localization": ["back", "planet"]})
    x = patient.encode(df)
    assert x.shape == (2, patient.N_FEATURES) and x.dtype == np.float32
    assert x[0, 0] == pytest.approx(0.45) and x[1, 1] == 1        # edad faltante
    assert x[1, 2 + patient.SEXES.index("unknown")] == 1
    assert x[1, 5 + patient.LOCALIZATIONS.index("unknown")] == 1
    fusion = build_two_view(single, {"hidden": 8})
    model = with_metadata(fusion, patient.N_FEATURES)
    rng = np.random.default_rng(0)
    a, b = (rng.uniform(0, 255, (2, SIZE, SIZE, 3)).astype("float32") for _ in range(2))
    np.testing.assert_allclose(model.predict({"view_a": a, "view_b": b, "metadata": x}, verbose=0),
                               fusion.predict({"view_a": a, "view_b": b}, verbose=0), atol=1e-6)


def test_two_view_fold_with_patient_data(tmp_path, single):
    rng = np.random.default_rng(2)
    df = lesions_df()
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    rows = []
    for copy in ("", "b"):
        for image_id in df.image_id + copy:
            tf.io.write_file(str(images_dir / f"{image_id}.jpg"),
                             tf.io.encode_jpeg(rng.integers(0, 255, (45, 60, 3), dtype=np.uint8)))
            rows.append({"image_id": image_id, "age": 50.0, "sex": "male", "localization": "back"})
    meta_csv = tmp_path / "metadata.csv"
    pd.DataFrame(rows).to_csv(meta_csv, index=False)
    other = df.assign(image_id=df.image_id + "b", lesion_id=df.lesion_id + "b")
    splits = pd.concat([df.assign(fold=0), other.assign(fold=1)]).assign(split="trainval")
    single.save(tmp_path / "single.keras")
    cfg = {"seed": 0, "model": MODEL_CFG, "pairs": {"max_lesions": None},
           "data": {"image_size": SIZE, "augmentation": {},
                    "sources": {"ham10000": {"metadata": str(meta_csv)}}},
           "fusion": {"hidden": 8}, "metadata": {"use": True, "hidden": 4},
           "view_degradation": None, "evaluation_degradations": {"dark": [0.5]},
           "training": {"batch_size": 2, "early_stopping_patience": 2,
                        "phases": {"head": {"epochs": 1, "learning_rate": 1e-3},
                                   "finetune": {"epochs": 1, "learning_rate": 1e-4}}}}
    pred, _ = two_view_fold(cfg, splits, 0, images_dir, tmp_path / "single.keras",
                            tmp_path / "fold_0", verbose=0)
    assert pred.fusion.between(0, 1).all() and pred["fusion_dark_0.5"].between(0, 1).all()
    assert (tmp_path / "fold_0" / "modelo.keras").exists()
