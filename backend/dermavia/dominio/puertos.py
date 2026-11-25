"""Interfaces que el dominio necesita de la infraestructura (inversión de dependencias).

Hay dos implementaciones de cada una: en memoria (pruebas y desarrollo local) y con los servicios
de Google Cloud (Firestore, Cloud Storage, Firebase). El dominio no importa ninguna biblioteca de
la nube.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import Protocol

from .modelos import (
    Caso, EstadoCaso, EventoAuditoria, Informe, Paciente, Rol, Usuario, Validacion,
)


class Reloj(Protocol):
    def ahora(self) -> datetime: ...


class RepoUsuarios(Protocol):
    def obtener(self, uid: str) -> Usuario | None: ...
    def guardar(self, usuario: Usuario) -> None: ...
    def listar(self) -> list[Usuario]: ...


class RepoPacientes(Protocol):
    def obtener(self, id_paciente: str) -> Paciente | None: ...
    def buscar_por_hc(self, numero_historia_clinica: str) -> Paciente | None: ...

    def crear(self, paciente: Paciente) -> None:
        """Lanza `Conflicto` si la historia clínica ya está registrada (es única)."""

    def guardar(self, paciente: Paciente) -> None: ...
    def listar(self) -> list[Paciente]: ...


class RepoCasos(Protocol):
    def obtener(self, id_caso: str) -> Caso | None: ...
    def crear(self, caso: Caso) -> None: ...
    def buscar_por_solicitud(self, uid_medico: str, id_solicitud: str) -> Caso | None: ...

    def actualizar(self, id_caso: str, cambio: Callable[[Caso], Caso]) -> Caso:
        """Aplica `cambio` al caso de forma atómica (transacción) y devuelve el caso nuevo.

        `cambio` puede lanzar un `ErrorDominio` para abortar sin escribir, y debe ser puro: en
        Firestore la transacción se reintenta si otro proceso modificó el caso. Lanza
        `NoEncontrado` si el caso no existe.
        """

    def listar_por_medico(self, uid_medico: str) -> list[Caso]: ...
    def listar_por_paciente(self, id_paciente: str) -> list[Caso]: ...
    def listar_por_estado(self, estado: EstadoCaso) -> list[Caso]: ...


class RepoValidaciones(Protocol):
    """Base de datos de solo inserción: no hay actualizar ni borrar (RF-04.4, RNF-04)."""

    def insertar(self, validacion: Validacion) -> None:
        """Lanza `Conflicto` si ya existe una validación con ese id."""

    def listar_por_caso(self, id_caso: str) -> list[Validacion]: ...


class RepoInformes(Protocol):
    def obtener_por_caso(self, id_caso: str) -> Informe | None: ...

    def insertar(self, informe: Informe) -> None:
        """Lanza `Conflicto` si el caso ya tiene informe (un caso se cierra una sola vez)."""


class RegistroAuditoria(Protocol):
    def registrar(self, evento: EventoAuditoria) -> None: ...
    def listar(self, limite: int) -> list[EventoAuditoria]: ...


class Almacen(Protocol):
    """Cloud Storage: las fotos se cargan desde la app con URL firmadas, sin pasar por el backend."""

    def url_subida(self, ruta: str, tipo_contenido: str, vigencia: timedelta) -> str: ...
    def url_lectura(self, ruta: str, vigencia: timedelta) -> str: ...

    def leer(self, ruta: str) -> bytes | None:
        """Contenido del objeto, o None si no existe."""


class Cuentas(Protocol):
    """Firebase Authentication con el Admin SDK."""

    def crear(self, correo: str, nombres: str) -> str:
        """Crea la cuenta sin contraseña y devuelve su uid. `Conflicto` si el correo ya existe."""

    def fijar_rol(self, uid: str, rol: Rol) -> None: ...

    def revocar_sesiones(self, uid: str) -> None: ...


class Push(Protocol):
    """Firebase Cloud Messaging. El contenido nunca lleva datos clínicos."""

    def enviar(self, tokens: Sequence[str], titulo: str, cuerpo: str,
               datos: dict[str, str]) -> list[str]:
        """Envía la notificación y devuelve los tokens que ya no son válidos."""


GeneradorIds = Callable[[], str]
