"""Módulo Auditoría: bitácora de eventos críticos (RNF-17) y métricas del modelo (RNF-14).

Cada evento se escribe como registro estructurado en Cloud Logging (bitácora con retención
bloqueada) y se guarda para la pantalla de bitácora del administrador (HU05). Las validaciones
llevan en `detalle` la concordancia entre el especialista y el modelo, con la versión del modelo,
para detectar su degradación (RF-03.6) con una métrica basada en registros.
"""

from __future__ import annotations

from .errores import PermisoDenegado
from .modelos import EventoAuditoria, TipoEvento, Usuario
from .puertos import GeneradorIds, RegistroAuditoria, Reloj


class ModuloAuditoria:
    def __init__(self, registro: RegistroAuditoria, reloj: Reloj, generar_id: GeneradorIds):
        self._registro = registro
        self._reloj = reloj
        self._generar_id = generar_id

    def registrar(self, tipo: TipoEvento, referencia: str, actor: Usuario | None = None,
                  **detalle: object) -> EventoAuditoria:
        evento = EventoAuditoria(
            id=self._generar_id(),
            tipo=tipo,
            referencia=referencia,
            uid_actor=actor.uid if actor else None,
            actor_nombre=actor.nombres if actor else "Sistema",
            fecha=self._reloj.ahora(),
            detalle=dict(detalle),
        )
        self._registro.registrar(evento)
        return evento

    def listar(self, admin: Usuario, limite: int = 200) -> list[EventoAuditoria]:
        if not admin.es_admin:
            raise PermisoDenegado()
        return self._registro.listar(limite)
