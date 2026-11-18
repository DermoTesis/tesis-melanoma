"""Validación del ID token de Firebase y del rol en cada solicitud (RNF-03).

No hay API Gateway (no existe en las regiones de Sudamérica): el propio servicio valida la
identidad. El rol y el acceso clínico se leen del perfil en Firestore en cada solicitud.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request

from ..contenedor import Contenedor
from ..dominio.errores import NoAutenticado
from ..dominio.modelos import Usuario


def contenedor(request: Request) -> Contenedor:
    return request.app.state.contenedor


def _token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise NoAutenticado()
    token = authorization[7:].strip()
    if not token:
        raise NoAutenticado()
    return token


Cont = Annotated[Contenedor, Depends(contenedor)]


def usuario_actual(c: Cont, authorization: Annotated[str | None, Header()] = None) -> Usuario:
    uid = c.verificador.verificar(_token(authorization))
    return c.identidad.autenticado(uid)


def clinico(c: Cont, usuario: Annotated[Usuario, Depends(usuario_actual)]) -> Usuario:
    return c.identidad.exigir_clinico(usuario)


def administrador(c: Cont, usuario: Annotated[Usuario, Depends(usuario_actual)]) -> Usuario:
    return c.identidad.exigir_admin(usuario)


def tarea_programada(c: Cont, authorization: Annotated[str | None, Header()] = None) -> None:
    c.verificador_tareas.verificar(_token(authorization))


Autenticado = Annotated[Usuario, Depends(usuario_actual)]
Clinico = Annotated[Usuario, Depends(clinico)]
Admin = Annotated[Usuario, Depends(administrador)]
