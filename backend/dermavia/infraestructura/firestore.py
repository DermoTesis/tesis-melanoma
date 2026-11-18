"""Repositorios sobre Firestore, en southamerica-west1 (Tabla 5 de la memoria).

- Base `(default)`: colecciones `usuarios`, `pacientes`, `historias_clinicas` (índice que hace
  única la historia clínica), `casos`, `informes` y `auditoria`.
- Base `validaciones`: colección `validaciones`, de solo inserción. Este adaptador no tiene
  ninguna operación de actualizar ni borrar, las inserciones usan `create` (falla si el
  documento ya existe) y las reglas de seguridad niegan todo acceso desde clientes
  (`firestore.rules`): solo el backend, con su cuenta de servicio, llega a los datos.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from google.api_core.exceptions import AlreadyExists, Conflict
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from ..dominio.errores import Conflicto, NoEncontrado
from ..dominio.modelos import (
    Caso, EstadoCaso, EventoAuditoria, Informe, Paciente, Usuario, Validacion,
)
from .documentos import a_documento, desde_documento

_YA_EXISTE = (AlreadyExists, Conflict)


def _donde(campo: str, valor: object) -> FieldFilter:
    return FieldFilter(campo, "==", valor)


class RepoUsuariosFirestore:
    def __init__(self, db: firestore.Client):
        self._col = db.collection("usuarios")

    def obtener(self, uid: str) -> Usuario | None:
        snap = self._col.document(uid).get()
        return desde_documento(Usuario, snap.to_dict()) if snap.exists else None

    def guardar(self, usuario: Usuario) -> None:
        self._col.document(usuario.uid).set(a_documento(usuario))

    def listar(self) -> list[Usuario]:
        return [desde_documento(Usuario, s.to_dict()) for s in self._col.stream()]


class RepoPacientesFirestore:
    def __init__(self, db: firestore.Client):
        self._db = db
        self._col = db.collection("pacientes")
        self._indice = db.collection("historias_clinicas")

    @staticmethod
    def _clave_hc(numero_historia_clinica: str) -> str:
        # El id de un documento no admite "/", que sí puede aparecer en una historia clínica.
        return hashlib.sha256(numero_historia_clinica.encode()).hexdigest()

    def obtener(self, id_paciente: str) -> Paciente | None:
        snap = self._col.document(id_paciente).get()
        return desde_documento(Paciente, snap.to_dict()) if snap.exists else None

    def buscar_por_hc(self, numero_historia_clinica: str) -> Paciente | None:
        snap = self._indice.document(self._clave_hc(numero_historia_clinica)).get()
        return self.obtener(snap.get("id_paciente")) if snap.exists else None

    def crear(self, paciente: Paciente) -> None:
        lote = self._db.batch()
        lote.create(self._indice.document(self._clave_hc(paciente.numero_historia_clinica)),
                    {"id_paciente": paciente.id})
        lote.create(self._col.document(paciente.id), a_documento(paciente))
        try:
            lote.commit()
        except _YA_EXISTE:
            raise Conflicto("Ya existe un paciente con esa historia clínica.") from None

    def guardar(self, paciente: Paciente) -> None:
        self._col.document(paciente.id).set(a_documento(paciente))

    def listar(self) -> list[Paciente]:
        return [desde_documento(Paciente, s.to_dict()) for s in self._col.stream()]


class RepoCasosFirestore:
    def __init__(self, db: firestore.Client):
        self._db = db
        self._col = db.collection("casos")

    def _consulta(self, campo: str, valor: object) -> list[Caso]:
        return [desde_documento(Caso, s.to_dict())
                for s in self._col.where(filter=_donde(campo, valor)).stream()]

    def obtener(self, id_caso: str) -> Caso | None:
        snap = self._col.document(id_caso).get()
        return desde_documento(Caso, snap.to_dict()) if snap.exists else None

    def crear(self, caso: Caso) -> None:
        try:
            self._col.document(caso.id).create(a_documento(caso))
        except _YA_EXISTE:
            raise Conflicto("El caso ya existe.") from None

    def buscar_por_solicitud(self, uid_medico: str, id_solicitud: str) -> Caso | None:
        consulta = (self._col.where(filter=_donde("uid_medico", uid_medico))
                    .where(filter=_donde("id_solicitud", id_solicitud)).limit(1))
        snaps = list(consulta.stream())
        return desde_documento(Caso, snaps[0].to_dict()) if snaps else None

    def actualizar(self, id_caso: str, cambio: Callable[[Caso], Caso]) -> Caso:
        referencia = self._col.document(id_caso)

        @firestore.transactional
        def en_transaccion(transaccion: firestore.Transaction) -> Caso:
            snap = referencia.get(transaction=transaccion)
            if not snap.exists:
                raise NoEncontrado("No se encontró el caso.")
            nuevo = cambio(desde_documento(Caso, snap.to_dict()))
            transaccion.set(referencia, a_documento(nuevo))
            return nuevo

        return en_transaccion(self._db.transaction())

    def listar_por_medico(self, uid_medico: str) -> list[Caso]:
        return self._consulta("uid_medico", uid_medico)

    def listar_por_paciente(self, id_paciente: str) -> list[Caso]:
        return self._consulta("id_paciente", id_paciente)

    def listar_por_estado(self, estado: EstadoCaso) -> list[Caso]:
        return self._consulta("estado", estado.value)


class RepoValidacionesFirestore:
    def __init__(self, db_validaciones: firestore.Client):
        self._col = db_validaciones.collection("validaciones")

    def insertar(self, validacion: Validacion) -> None:
        try:
            self._col.document(validacion.id).create(a_documento(validacion))
        except _YA_EXISTE:
            raise Conflicto("La validación ya existe.") from None

    def listar_por_caso(self, id_caso: str) -> list[Validacion]:
        validaciones = [desde_documento(Validacion, s.to_dict())
                        for s in self._col.where(filter=_donde("id_caso", id_caso)).stream()]
        return sorted(validaciones, key=lambda v: v.fecha_validacion)


class RepoInformesFirestore:
    def __init__(self, db: firestore.Client):
        self._col = db.collection("informes")

    def obtener_por_caso(self, id_caso: str) -> Informe | None:
        snap = self._col.document(id_caso).get()
        return desde_documento(Informe, snap.to_dict()) if snap.exists else None

    def insertar(self, informe: Informe) -> None:
        try:
            self._col.document(informe.id_caso).create(a_documento(informe))
        except _YA_EXISTE:
            raise Conflicto("El caso ya está cerrado.") from None


class RegistroAuditoriaFirestore:
    def __init__(self, db: firestore.Client):
        self._col = db.collection("auditoria")

    def registrar(self, evento: EventoAuditoria) -> None:
        self._col.document(evento.id).create(a_documento(evento))

    def listar(self, limite: int) -> list[EventoAuditoria]:
        consulta = self._col.order_by("fecha", direction=firestore.Query.DESCENDING).limit(limite)
        return [desde_documento(EventoAuditoria, s.to_dict()) for s in consulta.stream()]
