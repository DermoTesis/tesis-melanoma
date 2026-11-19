"""Conversión entre las entidades del dominio y los documentos de Firestore.

Es genérica: recorre los campos de cada dataclass con sus anotaciones de tipo. Los enums se
guardan como su valor, las tuplas como listas y las fechas sin hora (`date`) como Timestamp a
medianoche UTC, porque Firestore no tiene un tipo de fecha sola.
"""

from __future__ import annotations

import types
from dataclasses import fields, is_dataclass
from datetime import UTC, date, datetime
from enum import Enum
from functools import cache
from typing import Any, TypeVar, Union, get_args, get_origin, get_type_hints

T = TypeVar("T")


def a_documento(entidad: Any) -> dict[str, Any]:
    return {campo.name: _codificar(getattr(entidad, campo.name)) for campo in fields(entidad)}


def _codificar(valor: Any) -> Any:
    if is_dataclass(valor) and not isinstance(valor, type):
        return a_documento(valor)
    if isinstance(valor, Enum):
        return valor.value
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=UTC)
    if isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day, tzinfo=UTC)
    if isinstance(valor, (tuple, list)):
        return [_codificar(v) for v in valor]
    if isinstance(valor, dict):
        return {str(k): _codificar(v) for k, v in valor.items()}
    return valor


@cache
def _anotaciones(clase: type) -> dict[str, Any]:
    return get_type_hints(clase)


def desde_documento(clase: type[T], documento: dict[str, Any]) -> T:
    anotaciones = _anotaciones(clase)
    valores = {}
    for campo in fields(clase):  # type: ignore[arg-type]
        if campo.name in documento:
            valores[campo.name] = _decodificar(anotaciones[campo.name], documento[campo.name])
    return clase(**valores)


def _decodificar(tipo: Any, valor: Any) -> Any:
    if valor is None:
        return None
    origen = get_origin(tipo)
    if origen in (Union, types.UnionType):
        (interno,) = [a for a in get_args(tipo) if a is not type(None)]
        return _decodificar(interno, valor)
    if origen is tuple:
        return tuple(_decodificar(get_args(tipo)[0], v) for v in valor)
    if origen is dict:
        return dict(valor)
    if isinstance(tipo, type) and is_dataclass(tipo):
        return desde_documento(tipo, valor)
    if isinstance(tipo, type) and issubclass(tipo, Enum):
        return tipo(valor)
    if tipo is datetime:
        valor = valor if isinstance(valor, datetime) else datetime.fromisoformat(valor)
        return valor if valor.tzinfo else valor.replace(tzinfo=UTC)
    if tipo is date:
        if isinstance(valor, datetime):
            return valor.astimezone(UTC).date()
        return valor if isinstance(valor, date) else date.fromisoformat(valor)
    if tipo is float:
        return float(valor)
    return valor
