"""Endpoints de la API REST, agrupados por módulo de dominio (Tabla 6 de la memoria).

Los endpoints son síncronos (`def`): FastAPI los corre en su grupo de hilos, porque Firestore,
Cloud Storage y LiteRT bloquean. La lógica vive en los módulos; aquí solo se traduce HTTP.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from ..dominio.errores import NoEncontrado, PermisoDenegado
from ..dominio.modelos import DatosClinicos, Validacion
from .autenticacion import Admin, Autenticado, Clinico, Cont, tarea_programada
from .esquemas import (
    AltaEspecialistaIn, CasoIn, CasoOut, CierreIn, DispositivoIn, DocumentoInformeOut,
    EstadoCasoOut, EventoOut, InformeOut, PacienteIn, PacienteOut, PermisosIn, PrediccionOut,
    ResumenTareaOut, SaludOut, TextoIn, UrlSubidaIn, UrlSubidaOut, UsuarioOut, ValidacionIn,
    ValidacionOut,
)


def _validacion_out(v: Validacion) -> ValidacionOut:
    return ValidacionOut(
        id=v.id, id_caso=v.id_caso, especialista_nombre=v.especialista_nombre,
        numero_colegiatura=v.numero_colegiatura, decision=v.decision, clase_final=v.clase_final,
        sustento_clinico=v.sustento_clinico, fecha_validacion=v.fecha_validacion,
        examenes_adicionales=v.examenes_adicionales, sugerencia_tomada=v.sugerencia_tomada,
        complementa_de=v.complementa_de, prediccion_original=PrediccionOut.desde(
            v.prediccion_original))


# --- Sistema ---

sistema = APIRouter(tags=["Sistema"])


@sistema.get("/health", response_model=SaludOut)
def salud(c: Cont) -> SaludOut:
    return SaludOut(estado="ok", version_modelo=c.inferencia.version)


# --- Módulo Identidad ---

identidad = APIRouter(tags=["Identidad"])


@identidad.get("/users/me", response_model=UsuarioOut)
def mi_usuario(usuario: Autenticado):
    return usuario


@identidad.post("/users/me/terms", response_model=UsuarioOut)
def aceptar_alcance(c: Cont, usuario: Autenticado):
    return c.identidad.aceptar_terminos(usuario)


@identidad.post("/users/me/devices", status_code=status.HTTP_204_NO_CONTENT)
def registrar_dispositivo(c: Cont, usuario: Autenticado, datos: DispositivoIn) -> Response:
    c.identidad.registrar_dispositivo(usuario, datos.token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@identidad.get("/admin/users", response_model=list[UsuarioOut])
def listar_usuarios(c: Cont, admin: Admin):
    return c.identidad.listar_usuarios(admin)


@identidad.post("/admin/specialists", response_model=UsuarioOut,
                status_code=status.HTTP_201_CREATED)
def alta_especialista(c: Cont, admin: Admin, datos: AltaEspecialistaIn):
    return c.identidad.alta_especialista(admin, **datos.model_dump())


@identidad.patch("/admin/users/{uid}/role", response_model=UsuarioOut)
def cambiar_permisos(c: Cont, admin: Admin, uid: str, datos: PermisosIn):
    return c.identidad.cambiar_permisos(admin, uid, rol=datos.rol,
                                        acceso_clinico=datos.acceso_clinico)


@identidad.get("/admin/audit", response_model=list[EventoOut])
def bitacora(c: Cont, admin: Admin, limite: Annotated[int, Query(ge=1, le=500)] = 200):
    return c.auditoria.listar(admin, limite)


# --- Módulo Pacientes ---

pacientes = APIRouter(tags=["Pacientes"])


@pacientes.get("/patients", response_model=list[PacienteOut])
def buscar_pacientes(c: Cont, medico: Clinico,
                     hc: Annotated[str | None, Query(max_length=40)] = None):
    """Con `hc`, busca por número de historia clínica (lista vacía si no existe)."""
    if hc is not None:
        paciente = c.pacientes.buscar_por_hc(hc)
        return [paciente] if paciente else []
    return c.pacientes.listar()


@pacientes.post("/patients", response_model=PacienteOut, status_code=status.HTTP_201_CREATED)
def registrar_paciente(c: Cont, medico: Clinico, datos: PacienteIn):
    return c.pacientes.registrar(medico, **datos.model_dump())


@pacientes.get("/patients/{id_paciente}", response_model=PacienteOut)
def obtener_paciente(c: Cont, medico: Clinico, id_paciente: str):
    return c.pacientes.obtener(id_paciente)


@pacientes.post("/patients/{id_paciente}/consent", response_model=PacienteOut)
def registrar_consentimiento(c: Cont, medico: Clinico, id_paciente: str):
    return c.pacientes.registrar_consentimiento(medico, id_paciente)


@pacientes.delete("/patients/{id_paciente}/consent", response_model=PacienteOut)
def revocar_consentimiento(c: Cont, medico: Clinico, id_paciente: str):
    return c.pacientes.revocar_consentimiento(medico, id_paciente)


@pacientes.get("/patients/{id_paciente}/cases", response_model=list[CasoOut])
def casos_del_paciente(c: Cont, medico: Clinico, id_paciente: str):
    c.pacientes.obtener(id_paciente)
    return [CasoOut.desde(caso) for caso in c.casos.listar_por_paciente(medico, id_paciente)]


@pacientes.get("/patients/{id_paciente}/reports", response_model=list[DocumentoInformeOut],
               tags=["Informes"])
def historial_del_paciente(c: Cont, medico: Clinico, id_paciente: str):
    return [DocumentoInformeOut.desde(d) for d in c.informes.historial(id_paciente)]


# --- Módulos Gestión de Casos y Validación Clínica ---

casos = APIRouter(tags=["Gestión de Casos"])


@casos.post("/cases", response_model=CasoOut, status_code=status.HTTP_201_CREATED)
def registrar_caso(c: Cont, medico: Clinico, datos: CasoIn):
    clinicos = datos.datos_clinicos
    caso = c.casos.registrar(
        medico, datos.id_paciente,
        DatosClinicos(ubicacion_lesion=clinicos.ubicacion_lesion,
                      tiempo_aparicion=clinicos.tiempo_aparicion,
                      sintomas=tuple(clinicos.sintomas),
                      impresion_clinica=clinicos.impresion_clinica),
        id_solicitud=datos.id_solicitud)
    return CasoOut.desde(caso)


@casos.get("/cases", response_model=list[CasoOut])
def mis_casos(c: Cont, medico: Clinico):
    return [CasoOut.desde(caso) for caso in c.casos.listar_mios(medico)]


@casos.get("/cases/pending", response_model=list[CasoOut], tags=["Validación Clínica"])
def cola_de_validacion(c: Cont, medico: Clinico):
    """Casos pendientes de validación, de mayor a menor probabilidad preliminar (RF-06.2)."""
    return [CasoOut.desde(caso) for caso in c.casos.pendientes(medico)]


@casos.get("/cases/{id_caso}", response_model=CasoOut)
def detalle_caso(c: Cont, medico: Clinico, id_caso: str):
    caso = c.casos.obtener(medico, id_caso)
    return CasoOut.desde(caso, urls_imagenes=c.casos.urls_imagenes(caso))


@casos.get("/cases/{id_caso}/status", response_model=EstadoCasoOut)
def estado_caso(c: Cont, medico: Clinico, id_caso: str):
    caso = c.casos.obtener(medico, id_caso)
    return EstadoCasoOut(id=caso.id, estado=caso.estado, ultimo_error=caso.ultimo_error)


@casos.post("/cases/{id_caso}/upload-url", response_model=UrlSubidaOut)
def url_de_subida(c: Cont, medico: Clinico, id_caso: str, datos: UrlSubidaIn):
    url, ruta, vence = c.casos.url_subida(medico, id_caso, datos.vista, datos.tipo_contenido)
    return UrlSubidaOut(url=url, encabezados={"Content-Type": datos.tipo_contenido}, ruta=ruta,
                        vence=vence)


@casos.post("/cases/{id_caso}/submit", response_model=CasoOut)
def enviar_caso(c: Cont, medico: Clinico, id_caso: str):
    """Analiza las dos fotos dentro de la misma solicitud. Devuelve el caso en
    PENDIENTE_VALIDACION (con su predicción) o en ERROR_ANALISIS (se reintenta solo)."""
    return CasoOut.desde(c.casos.enviar(medico, id_caso))


@casos.put("/cases/{id_caso}/suggestion", response_model=CasoOut, tags=["Validación Clínica"])
def editar_sugerencia(c: Cont, medico: Clinico, id_caso: str, datos: TextoIn):
    return CasoOut.desde(c.casos.actualizar_sugerencia(medico, id_caso, datos.texto))


@casos.post("/cases/{id_caso}/notes", response_model=CasoOut)
def agregar_nota(c: Cont, medico: Clinico, id_caso: str, datos: TextoIn):
    return CasoOut.desde(c.casos.agregar_nota(medico, id_caso, datos.texto))


@casos.get("/cases/{id_caso}/validations", response_model=list[ValidacionOut],
           tags=["Validación Clínica"])
def validaciones_del_caso(c: Cont, medico: Clinico, id_caso: str):
    return [_validacion_out(v) for v in c.validacion.listar(medico, id_caso)]


@casos.post("/validations", response_model=ValidacionOut, status_code=status.HTTP_201_CREATED,
            tags=["Validación Clínica"])
def registrar_validacion(c: Cont, medico: Clinico, datos: ValidacionIn):
    return _validacion_out(c.validacion.registrar(medico, **datos.model_dump()))


# --- Módulo Informes ---

informes = APIRouter(tags=["Informes"])


@informes.post("/cases/{id_caso}/close", response_model=InformeOut)
def cerrar_caso(c: Cont, medico: Clinico, id_caso: str, datos: CierreIn):
    """Cierra el caso con la conducta clínica. Solo procede con una validación registrada."""
    return c.informes.cerrar(medico, id_caso, datos.conducta_clinica)


@informes.get("/reports/{id_caso}", response_model=DocumentoInformeOut)
def informe(c: Cont, medico: Clinico, id_caso: str):
    return DocumentoInformeOut.desde(c.informes.documento(id_caso))


# --- Tareas de Cloud Scheduler ---

tareas = APIRouter(prefix="/tasks", tags=["Tareas programadas"],
                   dependencies=[Depends(tarea_programada)])


@tareas.post("/reprocess", response_model=ResumenTareaOut)
def reprocesar(c: Cont):
    """Reintenta los casos en ERROR_ANALISIS y los análisis que quedaron a medias."""
    return ResumenTareaOut(resumen=c.casos.reprocesar())


@tareas.post("/overdue-alerts", response_model=ResumenTareaOut)
def alertar_vencidos(c: Cont):
    """Notifica al médico responsable los casos que superaron el tiempo límite (RF-04.5)."""
    return ResumenTareaOut(resumen=c.notificaciones.alertar_vencidos())


# --- Solo en modo local: Cloud Storage simulado ---

desarrollo = APIRouter(prefix="/dev/almacen", tags=["Desarrollo local"], include_in_schema=False)


def _almacen_local(c: Cont, ruta: str, metodo: str, vence: int, firma: str):
    from ..infraestructura.memoria import AlmacenLocal

    almacen = c.almacen
    if not c.es_local or not isinstance(almacen, AlmacenLocal):
        raise NoEncontrado()
    if not almacen.firma_valida(metodo, ruta, vence, firma):
        raise PermisoDenegado("La URL firmada no es válida o venció.")
    return almacen


@desarrollo.put("/{ruta:path}", status_code=status.HTTP_200_OK)
async def subir_local(c: Cont, request: Request, ruta: str, metodo: str, vence: int, firma: str):
    almacen = _almacen_local(c, ruta, "PUT", vence, firma)
    if metodo != "PUT":
        raise PermisoDenegado()
    almacen.poner(ruta, await request.body())
    return Response(status_code=status.HTTP_200_OK)


@desarrollo.get("/{ruta:path}")
def leer_local(c: Cont, ruta: str, metodo: str, vence: int, firma: str):
    almacen = _almacen_local(c, ruta, "GET", vence, firma)
    datos = almacen.leer(ruta)
    if datos is None or metodo != "GET":
        raise NoEncontrado()
    return Response(content=datos, media_type="application/octet-stream")

