"""EXP-04, paso 1: modelo final de una y de dos fotos con todo train + val (GPU).

    bash scripts/gpu.sh experiments/exp04_modelo_final.py

Repite el entrenamiento de EXP-03 (una foto, sin balanceo) y de EXP-06 (fusión) con todos los
datos de train + val; el test no entra. Como no queda validación para detenerse, cada fase entrena
la mediana de la mejor época de los 5 folds de esas corridas. La configuración de la fusión y de
la degradación de vistas se copia de EXP-06, para entrenar exactamente lo que se validó.
"""

from __future__ import annotations

import json
import statistics
import sys
from typing import Any

from melanoma.config import parse_cli
from melanoma.runs import PROJECT_ROOT, start_run

CONFIG = PROJECT_ROOT / "configs" / "exp04_calibracion.yaml"


def cv_phases(run_dir, run_cfg: dict[str, Any]) -> dict[str, Any]:
    """Las fases de la corrida, con el ajuste fino hasta la mediana de la mejor época."""
    training = json.loads((run_dir / "metricas.json").read_text())["details"]["training"]
    best = statistics.median(info["best_epoch"] for info in training.values())
    phases = json.loads(json.dumps(run_cfg["training"]["phases"]))
    phases["finetune"]["epochs"] = max(1, round(best) - phases["head"]["epochs"])
    return phases


def main(argv: list[str] | None = None) -> int:
    cfg, _ = parse_cli(__doc__.splitlines()[0], CONFIG, argv)
    import yaml

    from melanoma.data import ham10000
    from melanoma.data.splits import load_splits
    from melanoma.final_model import train_final
    from melanoma.training import run_isolated, setup_devices

    results = PROJECT_ROOT / cfg["paths"]["results"]
    single_dir, two_dir = results / cfg["single_view_run"], results / cfg["two_view_run"]
    single_cfg = yaml.safe_load((single_dir / "config.yaml").read_text())
    two_cfg = yaml.safe_load((two_dir / "config.yaml").read_text())

    def comparable(c: dict[str, Any], key: str) -> Any:
        return {k: v for k, v in c[key].items() if k != "max_images"} if key == "data" else c[key]

    for key in ("model", "split", "data", "seed"):
        if not (comparable(single_cfg, key) == comparable(two_cfg, key) == comparable(cfg, key)):
            raise SystemExit(f"`{key}` no coincide entre {cfg['single_view_run']}, "
                             f"{cfg['two_view_run']} y esta configuración")
    cfg["fusion"] = two_cfg["fusion"]
    cfg["view_degradation"] = two_cfg["view_degradation"]
    # `final` solo se pasa a mano en pruebas rápidas; si no, sale de la validación cruzada.
    cfg["final"] = cfg.get("final") or {"single_view": {"phases": cv_phases(single_dir, single_cfg)},
                                        "two_view": {"phases": cv_phases(two_dir, two_cfg)}}

    devices = setup_devices(cfg["training"])
    print(f"GPU: {devices['gpus'] or 'ninguna'}; precisión mixta: {devices['mixed_precision']}; "
          f"XLA: {devices['jit_compile']}")
    splits = load_splits(PROJECT_ROOT / cfg["paths"]["splits"] / cfg["split"]["name"])
    images_dir = PROJECT_ROOT / cfg["data"]["sources"]["ham10000"]["images"]
    missing = ham10000.missing_images(splits, images_dir)
    if missing:
        raise FileNotFoundError(f"Faltan {len(missing)} imágenes en {images_dir}, p. ej. {missing[:3]}")

    run = start_run(cfg, "exp04", "modelo-final")
    for name, part in cfg["final"].items():
        ph = part["phases"]
        print(f"{name}: {ph['head']['epochs']} épocas de cabeza + {ph['finetune']['epochs']} de "
              f"ajuste fino")
    print(f"Corrida {run.run_id}")
    info = run_isolated(train_final, cfg, splits, images_dir, run.artifacts_dir)
    rows = [{"model": name, "epochs": i["head_epochs"] + i["finetune_epochs"],
             "train_seconds": i["train_seconds"],
             "n_train": i.get("n_train_lesions", i.get("n_train_images"))}
            for name, i in info.items()]
    run.save_metrics(rows, details={"training": info, "devices": devices})
    print(f"Modelos en {run.artifacts_dir}; corrida registrada en {run.results_dir}")
    print(f"Para los pasos 2 y 3: --set final_run=exp04/{run.run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
