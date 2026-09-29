"""Carga de configuraciones YAML con herencia y sobrescrituras por línea de comandos.

Cada YAML de experimento declara `extends: base.yaml` (ruta relativa a su propio archivo) y solo
define lo que cambia. Desde la línea de comandos se sobrescribe con `--set seccion.clave=valor`,
donde el valor se interpreta como YAML.
"""

from __future__ import annotations

import argparse
import copy
import re
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml

EXTENDS_KEY = "extends"


class _Loader(yaml.SafeLoader):
    """SafeLoader que además lee `1e-3` como float (YAML 1.1 lo deja como texto)."""


_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(r"^[-+]?[0-9][0-9_]*(?:\.[0-9_]*)?[eE][-+]?[0-9]+$"),
    list("-+0123456789"),
)


def _yaml_load(text: str) -> Any:
    return yaml.load(text, Loader=_Loader)


def deep_merge(base: dict, override: dict) -> dict:
    """Copia de `base` con `override` aplicado; los diccionarios anidados se combinan por clave."""
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def load_config(path: str | Path, overrides: Iterable[str] = ()) -> dict:
    """Lee un YAML resolviendo su cadena de `extends` y aplica las sobrescrituras en orden."""
    cfg = _load_with_parents(Path(path), seen=())
    for item in overrides:
        key, value = parse_override(item)
        set_by_path(cfg, key, value)
    return cfg


def _load_with_parents(path: Path, seen: tuple[Path, ...]) -> dict:
    path = path.resolve()
    if path in seen:
        raise ValueError(f"Herencia circular de configuración en {path}")
    cfg = _yaml_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(cfg, dict):
        raise ValueError(f"{path} debe contener un diccionario en la raíz")
    parent = cfg.pop(EXTENDS_KEY, None)
    if parent is None:
        return cfg
    return deep_merge(_load_with_parents(path.parent / parent, seen + (path,)), cfg)


def parse_override(item: str) -> tuple[str, Any]:
    """Convierte `a.b=valor` en (`a.b`, valor interpretado como YAML)."""
    key, sep, raw = item.partition("=")
    key = key.strip()
    if not sep or not key:
        raise ValueError(f"Sobrescritura inválida {item!r}: se espera clave.subclave=valor")
    return key, _yaml_load(raw)


def get_by_path(cfg: dict, dotted: str) -> Any:
    node: Any = cfg
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(f"La configuración no tiene la clave {dotted!r}")
        node = node[part]
    return node


def set_by_path(cfg: dict, dotted: str, value: Any) -> None:
    *parents, leaf = dotted.split(".")
    node = cfg
    for part in parents:
        node = node.setdefault(part, {})
        if not isinstance(node, dict):
            raise KeyError(f"No se puede sobrescribir {dotted!r}: {part!r} no es una sección")
    node[leaf] = value


def parse_cli(description: str, default_config: str | Path,
              argv: Sequence[str] | None = None) -> tuple[dict, argparse.Namespace]:
    """Argumentos comunes de los scripts de `experiments/`: `--config` y `--set` (repetible)."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--config", default=str(default_config),
                        help="YAML del experimento (por defecto: %(default)s)")
    parser.add_argument("--set", dest="overrides", action="append", default=[],
                        metavar="CLAVE=VALOR", help="sobrescribe una clave, p. ej. training.batch_size=16")
    args = parser.parse_args(argv)
    return load_config(args.config, args.overrides), args
