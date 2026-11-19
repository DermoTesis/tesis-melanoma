"""Adaptadores en memoria: los usan las pruebas y el servidor local (`python -m dermavia.local`).

Respetan las mismas garantías que los de Firestore: la historia clínica es única, `actualizar`
es atómico, las validaciones y los informes solo se insertan.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from ..dominio.errores import Conflicto, NoEncontrado
from ..dominio.modelos import (
    Caso, EstadoCaso, EventoAuditoria, Informe, Paciente, Rol, Usuario, Validacion,
)


class RelojSistema:
    def ahora(self) -> datetime:
        return datetime.now(UTC)


def generar_id() -> str:
    """Identificador de 20 caracteres, como los que genera Firestore."""
    return uuid.uuid4().hex[:20]


class RepoUsuariosMemoria:
    def __init__(self):
        self._datos: dict[str, Usuario] = {}
        self._candado = threading.Lock()

    def obtener(self, uid: str) -> Usuario | None:
        return self._datos.get(uid)

    def guardar(self, usuario: Usuario) -> None:
        with self._candado:
            self._datos[usuario.uid] = usuario

    def listar(self) -> list[Usuario]:
        return list(self._datos.values())


class RepoPacientesMemoria:
    def __init__(self):
        self._datos: dict[str, Paciente] = {}
        self._por_hc: dict[str, str] = {}
        self._candado = threading.Lock()

    def obtener(self, id_paciente: str) -> Paciente | None:
        return self._datos.get(id_paciente)

    def buscar_por_hc(self, numero_historia_clinica: str) -> Paciente | None:
        id_paciente = self._por_hc.get(numero_historia_clinica)
        return self._datos.get(id_paciente) if id_paciente else None

    def crear(self, paciente: Paciente) -> None:
        with self._candado:
            if paciente.numero_historia_clinica in self._por_hc:
                raise Conflicto("Ya existe un paciente con esa historia clínica.")
            self._por_hc[paciente.numero_historia_clinica] = paciente.id
            self._datos[paciente.id] = paciente

    def guardar(self, paciente: Paciente) -> None:
        with self._candado:
            self._datos[paciente.id] = paciente

    def listar(self) -> list[Paciente]:
        return list(self._datos.values())


class RepoCasosMemoria:
    def __init__(self):
        self._datos: dict[str, Caso] = {}
        self._candado = threading.RLock()

    def obtener(self, id_caso: str) -> Caso | None:
        return self._datos.get(id_caso)

    def crear(self, caso: Caso) -> None:
        with self._candado:
            if caso.id in self._datos:
                raise Conflicto("El caso ya existe.")
            self._datos[caso.id] = caso

    def buscar_por_solicitud(self, uid_medico: str, id_solicitud: str) -> Caso | None:
        return next((c for c in self._datos.values()
                     if c.uid_medico == uid_medico and c.id_solicitud == id_solicitud), None)

    def actualizar(self, id_caso: str, cambio: Callable[[Caso], Caso]) -> Caso:
        with self._candado:
            actual = self._datos.get(id_caso)
            if actual is None:
                raise NoEncontrado("No se encontró el caso.")
            nuevo = cambio(actual)
            self._datos[id_caso] = nuevo
            return nuevo

    def listar_por_medico(self, uid_medico: str) -> list[Caso]:
        return [c for c in self._datos.values() if c.uid_medico == uid_medico]

    def listar_por_paciente(self, id_paciente: str) -> list[Caso]:
        return [c for c in self._datos.values() if c.id_paciente == id_paciente]

    def listar_por_estado(self, estado: EstadoCaso) -> list[Caso]:
        return [c for c in self._datos.values() if c.estado == estado]


class RepoValidacionesMemoria:
    def __init__(self):
        self._datos: dict[str, Validacion] = {}
        self._candado = threading.Lock()

    def insertar(self, validacion: Validacion) -> None:
        with self._candado:
            if validacion.id in self._datos:
                raise Conflicto("La validación ya existe.")
            self._datos[validacion.id] = validacion

    def listar_por_caso(self, id_caso: str) -> list[Validacion]:
        return sorted((v for v in self._datos.values() if v.id_caso == id_caso),
                      key=lambda v: v.fecha_validacion)


class RepoInformesMemoria:
    def __init__(self):
        self._datos: dict[str, Informe] = {}
        self._candado = threading.Lock()

    def obtener_por_caso(self, id_caso: str) -> Informe | None:
        return self._datos.get(id_caso)

    def insertar(self, informe: Informe) -> None:
        with self._candado:
            if informe.id_caso in self._datos:
                raise Conflicto("El caso ya está cerrado.")
            self._datos[informe.id_caso] = informe


class RegistroAuditoriaMemoria:
    def __init__(self):
        self.eventos: list[EventoAuditoria] = []
        self._candado = threading.Lock()

    def registrar(self, evento: EventoAuditoria) -> None:
        with self._candado:
            self.eventos.append(evento)

    def listar(self, limite: int) -> list[EventoAuditoria]:
        return sorted(self.eventos, key=lambda e: e.fecha, reverse=True)[:limite]


class AlmacenMemoria:
    """Cloud Storage simulado: las pruebas cargan las fotos con `poner`."""

    def __init__(self):
        self.objetos: dict[str, bytes] = {}

    def poner(self, ruta: str, datos: bytes) -> None:
        self.objetos[ruta] = datos

    def url_subida(self, ruta: str, tipo_contenido: str, vigencia: timedelta) -> str:
        return f"memoria://subida/{ruta}?tipo={quote(tipo_contenido)}"

    def url_lectura(self, ruta: str, vigencia: timedelta) -> str:
        return f"memoria://lectura/{ruta}"

    def leer(self, ruta: str) -> bytes | None:
        return self.objetos.get(ruta)


class AlmacenLocal:
    """Cloud Storage en una carpeta, con URL firmadas por HMAC (solo para el servidor local).

    Las URL apuntan a `/dev/almacen/...` del mismo servidor, que solo existe en modo local.
    """

    def __init__(self, carpeta: Path, url_base: str, secreto: bytes | None = None):
        self.carpeta = carpeta
        self.url_base = url_base.rstrip("/")
        self._secreto = secreto or uuid.uuid4().bytes

    def _firma(self, metodo: str, ruta: str, vence: int) -> str:
        mensaje = f"{metodo}\n{ruta}\n{vence}".encode()
        digest = hmac.new(self._secreto, mensaje, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")

    def _url(self, metodo: str, ruta: str, vigencia: timedelta) -> str:
        vence = int(time.time() + vigencia.total_seconds())
        firma = self._firma(metodo, ruta, vence)
        return f"{self.url_base}/dev/almacen/{ruta}?metodo={metodo}&vence={vence}&firma={firma}"

    def firma_valida(self, metodo: str, ruta: str, vence: int, firma: str) -> bool:
        return vence >= time.time() and hmac.compare_digest(firma, self._firma(metodo, ruta, vence))

    def _archivo(self, ruta: str) -> Path:
        archivo = (self.carpeta / ruta).resolve()
        if not archivo.is_relative_to(self.carpeta.resolve()):
            raise ValueError("Ruta fuera del almacén")
        return archivo

    def url_subida(self, ruta: str, tipo_contenido: str, vigencia: timedelta) -> str:
        return self._url("PUT", ruta, vigencia)

    def url_lectura(self, ruta: str, vigencia: timedelta) -> str:
        return self._url("GET", ruta, vigencia)

    def poner(self, ruta: str, datos: bytes) -> None:
        archivo = self._archivo(ruta)
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_bytes(datos)

    def leer(self, ruta: str) -> bytes | None:
        archivo = self._archivo(ruta)
        return archivo.read_bytes() if archivo.is_file() else None


class CuentasMemoria:
    """Firebase Authentication simulado."""

    def __init__(self):
        self.correos: dict[str, str] = {}
        self.roles: dict[str, Rol] = {}
        self.revocadas: list[str] = []

    def crear(self, correo: str, nombres: str) -> str:
        if correo in self.correos.values():
            raise Conflicto("Ya existe una cuenta con ese correo.")
        uid = generar_id()
        self.correos[uid] = correo
        return uid

    def fijar_rol(self, uid: str, rol: Rol) -> None:
        self.roles[uid] = rol

    def revocar_sesiones(self, uid: str) -> None:
        self.revocadas.append(uid)


class PushMemoria:
    """Firebase Cloud Messaging simulado: guarda lo que se habría enviado."""

    def __init__(self, invalidos: Sequence[str] = ()):
        self.enviados: list[dict[str, object]] = []
        self._invalidos = set(invalidos)

    def enviar(self, tokens: Sequence[str], titulo: str, cuerpo: str,
               datos: dict[str, str]) -> list[str]:
        self.enviados.append({"tokens": list(tokens), "titulo": titulo, "cuerpo": cuerpo,
                              "datos": dict(datos)})
        return [t for t in tokens if t in self._invalidos]


class VerificadorDesarrollo:
    """Solo en modo local: el token `dev:<uid>` identifica al usuario sin Firebase."""

    def verificar(self, token: str) -> str:
        from ..dominio.errores import NoAutenticado

        if not token.startswith("dev:") or len(token) <= 4:
            raise NoAutenticado()
        return token[4:]


class VerificadorTareasDesarrollo:
    """Solo en modo local: Cloud Scheduler se simula con el token `dev-tareas`."""

    def verificar(self, token: str) -> None:
        from ..dominio.errores import NoAutenticado

        if token != "dev-tareas":
            raise NoAutenticado()
