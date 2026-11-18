"""Registros estructurados en JSON por la salida estándar, que Cloud Run envía a Cloud Logging.

Cada evento de auditoría se escribe con `"tipo_registro": "auditoria"`, para enrutarlo con un
sink a un bucket de registros con retención bloqueada y para definir métricas basadas en
registros (por ejemplo, la concordancia de las validaciones por versión del modelo, RNF-14).
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from enum import Enum

from ..dominio.modelos import EventoAuditoria
from ..dominio.puertos import RegistroAuditoria

_NIVELES = {"WARNING": "WARNING", "ERROR": "ERROR", "CRITICAL": "CRITICAL", "DEBUG": "DEBUG"}


def _serializable(valor: object) -> object:
    if isinstance(valor, datetime):
        return valor.isoformat()
    if isinstance(valor, Enum):
        return valor.value
    return str(valor)


class FormatoJson(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entrada: dict[str, object] = {
            "severity": _NIVELES.get(record.levelname, "INFO"),
            "message": record.getMessage(),
            "logger": record.name,
        }
        entrada.update(getattr(record, "campos_json", {}))
        if record.exc_info:
            entrada["stack_trace"] = self.formatException(record.exc_info)
        return json.dumps(entrada, ensure_ascii=False, default=_serializable)


def configurar_logging(nivel: int = logging.INFO) -> None:
    manejador = logging.StreamHandler(sys.stdout)
    manejador.setFormatter(FormatoJson())
    raiz = logging.getLogger()
    raiz.handlers[:] = [manejador]
    raiz.setLevel(nivel)


_log_auditoria = logging.getLogger("dermavia.auditoria")


class RegistroAuditoriaConLogging:
    """Escribe el evento en Cloud Logging y lo guarda en el repositorio (bitácora del admin)."""

    def __init__(self, destino: RegistroAuditoria):
        self._destino = destino

    def registrar(self, evento: EventoAuditoria) -> None:
        _log_auditoria.info(
            f"{evento.tipo.value} · {evento.referencia}",
            extra={"campos_json": {
                "tipo_registro": "auditoria",
                "evento": {
                    "id": evento.id, "tipo": evento.tipo.value, "referencia": evento.referencia,
                    "uid_actor": evento.uid_actor, "actor_nombre": evento.actor_nombre,
                    "fecha": evento.fecha, "detalle": evento.detalle,
                },
            }},
        )
        self._destino.registrar(evento)

    def listar(self, limite: int) -> list[EventoAuditoria]:
        return self._destino.listar(limite)
