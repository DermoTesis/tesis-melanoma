"""Registro de corridas: cada corrida guarda su configuración, su entorno y sus métricas.

- `resultados/<experimento>/<id>/` (en git): `config.yaml`, `entorno.json` y `metricas.json`.
- `outputs/<experimento>/<id>/` (fuera de git): modelos, checkpoints y predicciones.
- `resultados/resultados.csv` se regenera a partir de todos los `metricas.json`, así que nunca
  hay que editarlo a mano ni resolver conflictos de git en él (basta con regenerarlo:
  `python -m melanoma.runs`). Es la tabla que alimenta el capítulo 6.

`metricas.json` tiene dos claves: `rows`, una lista de filas planas (una por candidato y fold)
que pasan al CSV, y `details`, con todo lo que no cabe en una fila (curvas, IC, matrices).
"""

from __future__ import annotations

import csv
import json
import os
import platform
import re
import socket
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_CSV = "resultados.csv"
TRACKED_PACKAGES = ("numpy", "pandas", "scikit-learn", "tensorflow", "keras", "torch", "ai-edge-litert")


@dataclass(frozen=True)
class Run:
    experiment: str
    run_id: str
    results_dir: Path
    artifacts_dir: Path

    def save_metrics(self, rows: list[dict[str, Any]], details: dict[str, Any] | None = None) -> Path:
        """Escribe `metricas.json` y regenera el `resultados.csv` consolidado."""
        payload = {"experiment": self.experiment, "run_id": self.run_id,
                   "rows": rows, "details": details or {}}
        path = self.results_dir / "metricas.json"
        _write_json(path, payload)
        consolidate_results(self.results_dir.parents[1])
        return path


def start_run(cfg: dict, experiment: str, name: str, root: Path = PROJECT_ROOT) -> Run:
    """Crea las carpetas de la corrida y guarda la configuración resuelta y el entorno."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{stamp}_{_slug(name)}"
    results_dir = root / cfg["paths"]["results"] / experiment / run_id
    artifacts_dir = root / cfg["paths"]["outputs"] / experiment / run_id
    env = environment_info(root, ignore=(cfg["paths"]["results"],))
    results_dir.mkdir(parents=True, exist_ok=False)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    (results_dir / "config.yaml").write_text(
        yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True), encoding="utf-8")
    _write_json(results_dir / "entorno.json", env)
    if env["git"].get("dirty"):
        print("Aviso: hay cambios sin commit; la corrida no será reproducible desde el commit "
              f"{env['git'].get('commit')}.", file=sys.stderr)
    return Run(experiment, run_id, results_dir, artifacts_dir)


def reopen_run(cfg: dict, ref: str, ignore: tuple[str, ...] = ("resume", "paths."),
               root: Path = PROJECT_ROOT) -> Run:
    """Retoma la corrida `<experimento>/<id>` (p. ej. después de que se apague la PC).

    Exige la misma configuración que la guardada (salvo las claves de `ignore`). Guarda el entorno
    de cada reanudación y avisa si el commit cambió, porque entonces la corrida mezcla versiones
    del código.
    """
    from melanoma.config import differences

    experiment, _, run_id = ref.partition("/")
    results_dir = root / cfg["paths"]["results"] / experiment / run_id
    artifacts_dir = root / cfg["paths"]["outputs"] / experiment / run_id
    if not (results_dir / "config.yaml").is_file():
        raise SystemExit(f"No existe la corrida {ref} en {results_dir.parent}")
    saved = yaml.safe_load((results_dir / "config.yaml").read_text(encoding="utf-8"))
    different = differences(cfg, saved, ignore)
    if different:
        raise SystemExit(f"La configuración no coincide con la de {ref}; difiere en: "
                         f"{', '.join(different)}")
    env = environment_info(root, ignore=(cfg["paths"]["results"],))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    _write_json(results_dir / f"entorno_reanudacion_{stamp}.json", env)
    first = json.loads((results_dir / "entorno.json").read_text(encoding="utf-8"))
    if first.get("git", {}).get("commit") != env["git"].get("commit"):
        print(f"Aviso: el commit cambió desde que empezó la corrida ({first.get('git', {}).get('commit')}"
              f" → {env['git'].get('commit')}); la corrida mezcla dos versiones del código.",
              file=sys.stderr)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return Run(experiment, run_id, results_dir, artifacts_dir)


def environment_info(root: Path = PROJECT_ROOT, ignore: tuple[str, ...] = ()) -> dict[str, Any]:
    """Versiones, hardware y commit: lo necesario para reproducir o explicar una corrida.

    `ignore`: rutas versionadas que no cuentan como cambios sin commit (los resultados).
    """
    versions = {}
    for package in TRACKED_PACKAGES:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return {
        "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "host": socket.gethostname(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "wsl": _is_wsl(),
        "docker": Path("/.dockerenv").exists(),
        "colab": "COLAB_RELEASE_TAG" in os.environ,
        "keras_backend": os.environ.get("KERAS_BACKEND"),
        "cpu_count": os.cpu_count(),
        "gpu": _nvidia_smi(),
        "packages": versions,
        "git": _git_info(root, ignore),
    }


def consolidate_results(results_root: Path) -> Path:
    """Reescribe `resultados.csv` con las filas de todos los `metricas.json`."""
    rows = []
    for path in sorted(results_root.glob("*/*/metricas.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for row in payload.get("rows", []):
            rows.append({"experiment": payload["experiment"], "run_id": payload["run_id"], **row})
    fieldnames: list[str] = []
    for row in rows:
        fieldnames.extend(k for k in row if k not in fieldnames)
    out = results_root / RESULTS_CSV
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return out


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default) + "\n",
                    encoding="utf-8")


def _json_default(obj: Any) -> Any:
    # Escalares y arreglos de numpy, sin importar numpy aquí.
    if hasattr(obj, "tolist"):
        return obj.tolist()
    if isinstance(obj, Path):
        return str(obj)
    raise TypeError(f"No se puede serializar {type(obj).__name__} a JSON")


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "corrida"


def _is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def _run(cmd: list[str], cwd: Path | None = None) -> str | None:
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _nvidia_smi() -> list[str]:
    out = _run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader"])
    return out.splitlines() if out else []


def _git_info(root: Path, ignore: tuple[str, ...] = ()) -> dict[str, Any]:
    commit = _run(["git", "rev-parse", "HEAD"], cwd=root)
    if commit is None:
        # Sin git (p. ej., en la imagen de NVIDIA): el commit se lee de .git, sin saber si hay
        # cambios sin commit.
        commit = _read_head(root / ".git")
        return {"commit": commit, "dirty": None} if commit else {}
    # Solo cuentan los archivos versionados modificados, sin los resultados: si no, la corrida
    # que regenera resultados.csv dejaba "sucias" a las siguientes del mismo experimento.
    excluded = [f":(exclude){p}" for p in ignore if not Path(p).is_absolute()]
    status = _run(["git", "status", "--porcelain", "--untracked-files=no", "--", ".", *excluded],
                  cwd=root)
    return {"commit": commit, "dirty": None if status is None else bool(status)}


def _read_head(git_dir: Path) -> str | None:
    try:
        head = (git_dir / "HEAD").read_text().strip()
        if not head.startswith("ref: "):
            return head or None
        ref = head.removeprefix("ref: ")
        if (git_dir / ref).is_file():
            return (git_dir / ref).read_text().strip()
        for line in (git_dir / "packed-refs").read_text().splitlines():
            if line.endswith(" " + ref):
                return line.split()[0]
    except OSError:
        pass
    return None


if __name__ == "__main__":
    from melanoma.config import load_config

    base = load_config(PROJECT_ROOT / "configs" / "base.yaml")
    print(consolidate_results(PROJECT_ROOT / base["paths"]["results"]))
