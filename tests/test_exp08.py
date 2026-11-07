"""Partes de EXP-08 que no entrenan: configuración por etapa, unión de predicciones y criterio."""

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

from melanoma.config import load_config

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("exp08", ROOT / "experiments" / "exp08_perdidas.py")
exp08 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp08)
CFG = load_config(ROOT / "configs" / "exp08_perdidas.yaml")


def test_stage_config_combines_base_stage_and_loss():
    single = exp08.stage_config(CFG, "focal", 142, "single_view")
    assert single["seed"] == 142
    assert single["training"]["imbalance"] == "focal_loss"
    assert single["training"]["focal_alpha"] == 0.25
    assert single["training"]["phases"]["finetune"]["epochs"] == 30
    assert single["training"]["batch_size"] == 32 and single["model"]["dropout"] == 0.2
    assert not set(exp08.EXPERIMENT_KEYS) & set(single)

    two = exp08.stage_config(CFG, "asl", 242, "two_view")
    assert two["training"]["imbalance"] == "asymmetric_loss"
    assert two["training"]["phases"]["head"]["epochs"] == 10
    assert two["training"]["phases"]["finetune"]["epochs"] == 25
    assert two["pairs"]["seed"] == 42 and two["seed"] == 242
    assert exp08.stage_config(CFG, "bce", 42, "two_view")["training"]["imbalance"] == "none"


def test_two_view_stage_is_exp06_with_more_epochs():
    exp06 = load_config(ROOT / "configs" / "exp06_dos_fotos.yaml")
    two = CFG["two_view"]
    for key in ("fusion", "view_degradation", "evaluation_degradations"):
        assert two[key] == exp06[key], key
    # Los pares de validación de EXP-06 salen de la semilla 42 + fold.
    assert two["pairs"]["seed"] == exp06["seed"]
    assert two["training"]["phases"]["head"] == exp06["training"]["phases"]["head"]
    assert two["training"]["phases"]["finetune"]["learning_rate"] == \
        exp06["training"]["phases"]["finetune"]["learning_rate"]


def _fake_fold(artifacts, variant, seed, stage, image_b="ISIC_2"):
    d = exp08.fold_dir(artifacts, variant, seed, stage, 0)
    d.mkdir(parents=True)
    if stage == "single_view":
        df = pd.DataFrame({"image_id": ["ISIC_1", "ISIC_2"], "lesion_id": ["L1", "L2"],
                           "dx": ["mel", "nv"], "label": [1, 0], "fold": [0, 0], "prob": [0.9, 0.2]})
    else:
        df = pd.DataFrame({"lesion_id": ["L1"], "image_a": ["ISIC_1"], "image_b": [image_b],
                           "label": [1], "dx": ["mel"], "dataset": ["rosendahl"], "fold": [0],
                           "fusion": [0.8], "single_a": [0.7], "average": [0.75], "weight_a": [0.5]})
    df.to_csv(d / "predicciones.csv", index=False)
    (d / "info.json").write_text("{}")


def test_collect_joins_variants_and_requires_the_same_pairs(tmp_path):
    cfg = {"seeds": [42], "variants": {"bce": {}, "asl": {}}, "folds": [0]}
    for variant in cfg["variants"]:
        _fake_fold(tmp_path, variant, 42, "single_view")
    wide = exp08.collect(cfg, tmp_path, "single_view")
    assert list(wide.columns[-2:]) == ["bce_s42", "asl_s42"] and len(wide) == 2

    _fake_fold(tmp_path, "bce", 42, "two_view")
    _fake_fold(tmp_path, "asl", 42, "two_view", image_b="ISIC_3")   # otro par: no comparable
    with pytest.raises(SystemExit, match="mismas"):
        exp08.collect(cfg, tmp_path, "two_view")
    assert exp08.is_done(exp08.fold_dir(tmp_path, "asl", 42, "two_view", 0))
    assert not exp08.is_done(exp08.fold_dir(tmp_path, "asl", 142, "two_view", 0))


@pytest.mark.parametrize("ci_low, by_seed, spec_high, expected", [
    (0.001, [0.01, 0.02, 0.005], 0.01, "cumple"),
    (-0.001, [0.01, 0.02, 0.005], 0.01, "no cumple"),     # a: el IC toca el 0
    (0.001, [0.01, -0.002, 0.03], 0.01, "no cumple"),     # b: una semilla empeora
    (0.001, [0.01, 0.02, 0.005], -0.01, "no cumple"),     # c: la especificidad empeora
])
def test_verdict_needs_the_three_conditions(ci_low, by_seed, spec_high, expected):
    comparison = {"delta_auc_roc_ci_low": ci_low, "delta_auc_roc_by_seed": by_seed,
                  "delta_specificity_s90_ci_high": spec_high}
    assert exp08.verdict(comparison, "s90") == expected
