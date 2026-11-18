"""Aplicación FastAPI. En Cloud Run: `uvicorn dermavia.main:create_app --factory`."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import __version__
from .config import Configuracion
from .contenedor import Contenedor, construir
from .dominio.errores import DatosInvalidos, ErrorDominio
from .infraestructura.registro import configurar_logging
from .presentacion import rutas
from .presentacion.esquemas import RespuestaError

log = logging.getLogger(__name__)

DESCRIPCION = """
Backend de Dermavía, herramienta de apoyo diagnóstico para melanoma de uso exclusivo del médico
especialista. Toda predicción es preliminar y requiere validación médica: ningún caso se cierra
ni genera su informe sin una validación registrada (RF-07.1).

Autenticación: `Authorization: Bearer <ID token de Firebase>` en todas las rutas salvo `/health`.
Los errores llegan como `{"error": {"codigo", "mensaje"}}`; el mensaje se puede mostrar tal cual.
"""


def create_app(contenedor: Contenedor | None = None) -> FastAPI:
    if contenedor is None:
        configurar_logging()
        contenedor = construir(Configuracion.desde_entorno())

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        # Cargar el modelo al arrancar la instancia, no en el primer caso. Si falla, el servicio
        # igual atiende (validaciones, informes) y el modelo se reintenta en el siguiente caso.
        try:
            await run_in_threadpool(app.state.contenedor.inferencia.calentar)
        except Exception:
            log.exception("No se pudo cargar el modelo al arrancar")
        yield

    app = FastAPI(
        title="Dermavía API", version=__version__, description=DESCRIPCION,
        lifespan=ciclo_de_vida,
        responses={code: {"model": RespuestaError} for code in (401, 403, 404, 409, 422)},
    )
    app.state.contenedor = contenedor

    @app.exception_handler(ErrorDominio)
    async def error_de_negocio(request: Request, error: ErrorDominio) -> JSONResponse:
        return JSONResponse(status_code=error.estado_http,
                            content={"error": {"codigo": error.codigo, "mensaje": error.mensaje}})

    @app.exception_handler(RequestValidationError)
    async def error_de_formato(request: Request, error: RequestValidationError) -> JSONResponse:
        campos = [".".join(str(p) for p in e["loc"][1:]) for e in error.errors()]
        return JSONResponse(status_code=422, content={"error": {
            "codigo": DatosInvalidos.codigo,
            "mensaje": DatosInvalidos.mensaje_por_defecto,
            "campos": campos,
        }})

    for router in (rutas.sistema, rutas.identidad, rutas.pacientes, rutas.casos, rutas.informes,
                   rutas.tareas):
        app.include_router(router)
    if contenedor.es_local:
        app.include_router(rutas.desarrollo)
    return app
