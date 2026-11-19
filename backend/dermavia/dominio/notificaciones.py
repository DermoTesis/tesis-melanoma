"""Módulo Notificaciones: alerta push al médico responsable de los casos vencidos (RF-04.5, HU24).

Lo invoca la tarea periódica de Cloud Scheduler. Se manda una sola notificación por médico, con
un texto genérico y sin datos clínicos (Tabla 7 de la memoria), y cada caso se alerta una vez.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta

from .auditoria import ModuloAuditoria
from .casos import ModuloCasos
from .identidad import ModuloIdentidad
from .modelos import Caso, TipoEvento
from .puertos import Push

log = logging.getLogger(__name__)

TITULO = "Dermavía"
CUERPO = "Tienes casos pendientes de validación que superaron el tiempo límite."


class ModuloNotificaciones:
    def __init__(self, casos: ModuloCasos, identidad: ModuloIdentidad, push: Push,
                 auditoria: ModuloAuditoria, limite: timedelta = timedelta(hours=48)):
        self._casos = casos
        self._identidad = identidad
        self._push = push
        self._auditoria = auditoria
        self._limite = limite

    def alertar_vencidos(self) -> dict[str, int]:
        por_medico: dict[str, list[Caso]] = defaultdict(list)
        for caso in self._casos.vencidos(self._limite):
            por_medico[caso.uid_medico].append(caso)

        resumen = {"casos": 0, "medicos": 0, "sin_dispositivo": 0}
        for uid, casos in por_medico.items():
            medico = self._identidad.obtener(uid)
            tokens = list(medico.tokens_dispositivo) if medico else []
            if tokens:
                try:
                    invalidos = self._push.enviar(
                        tokens, TITULO, CUERPO, {"tipo": "casos_vencidos"})
                except Exception:
                    log.exception("No se pudo enviar la alerta al médico %s", uid)
                    continue  # se reintenta en la siguiente ejecución
                self._identidad.quitar_tokens(uid, invalidos)
                resumen["medicos"] += 1
            else:
                # La alerta igual queda en el panel (pantalla de alertas de la app).
                resumen["sin_dispositivo"] += 1
            for caso in casos:
                self._casos.marcar_alertado(caso.id)
                self._auditoria.registrar(TipoEvento.ALERTA_VENCIDO, caso.id)
                resumen["casos"] += 1
        return resumen
