"""Raíz de composición: arma los módulos de dominio con los adaptadores de cada entorno."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Protocol

from .config import ARTEFACTO_LOCAL, Configuracion
from .dominio.auditoria import ModuloAuditoria
from .dominio.casos import ModuloCasos
from .dominio.identidad import ModuloIdentidad
from .dominio.inferencia import Artefacto, ModuloInferencia, Motor, MotorLiteRT
from .dominio.informes import ModuloInformes
from .dominio.notificaciones import ModuloNotificaciones
from .dominio.pacientes import ModuloPacientes
from .dominio.puertos import (
    Almacen, Cuentas, GeneradorIds, Push, RegistroAuditoria, Reloj, RepoCasos, RepoInformes,
    RepoPacientes, RepoUsuarios, RepoValidaciones,
)
from .dominio.validacion import ModuloValidacion
from .infraestructura import memoria
from .infraestructura.registro import RegistroAuditoriaConLogging


class VerificadorTokens(Protocol):
    def verificar(self, token: str) -> str:
        """uid del dueño del ID token; lanza `NoAutenticado` si no es válido."""


class VerificadorTareas(Protocol):
    def verificar(self, token: str) -> None:
        """Lanza `NoAutenticado` o `PermisoDenegado` si la llamada no viene de Cloud Scheduler."""


@dataclass
class Contenedor:
    reloj: Reloj
    auditoria: ModuloAuditoria
    identidad: ModuloIdentidad
    pacientes: ModuloPacientes
    inferencia: ModuloInferencia
    casos: ModuloCasos
    validacion: ModuloValidacion
    informes: ModuloInformes
    notificaciones: ModuloNotificaciones
    verificador: VerificadorTokens
    verificador_tareas: VerificadorTareas
    almacen: Almacen
    es_local: bool = False


def ensamblar(*, usuarios: RepoUsuarios, pacientes: RepoPacientes, casos: RepoCasos,
              validaciones: RepoValidaciones, informes: RepoInformes,
              registro: RegistroAuditoria, almacen: Almacen, cuentas: Cuentas, push: Push,
              cargar_artefacto: Callable[[], Artefacto], verificador: VerificadorTokens,
              verificador_tareas: VerificadorTareas, reloj: Reloj | None = None,
              generar_id: GeneradorIds = memoria.generar_id,
              crear_motor: Callable[[Artefacto], Motor] | None = None, hilos_inferencia: int = 2,
              horas_vencimiento: float = 48.0, es_local: bool = False) -> Contenedor:
    reloj = reloj or memoria.RelojSistema()
    auditoria = ModuloAuditoria(registro, reloj, generar_id)
    identidad = ModuloIdentidad(usuarios, cuentas, auditoria, reloj)
    modulo_pacientes = ModuloPacientes(pacientes, auditoria, reloj, generar_id)
    inferencia = ModuloInferencia(
        cargar_artefacto, reloj,
        crear_motor or (lambda artefacto: MotorLiteRT(artefacto, hilos_inferencia)))
    modulo_casos = ModuloCasos(casos, modulo_pacientes, inferencia, almacen, auditoria, reloj,
                               generar_id)
    validacion = ModuloValidacion(validaciones, modulo_casos, auditoria, reloj, generar_id)
    modulo_informes = ModuloInformes(informes, modulo_casos, validacion, modulo_pacientes,
                                     identidad, auditoria, reloj)
    notificaciones = ModuloNotificaciones(modulo_casos, identidad, push, auditoria,
                                          timedelta(hours=horas_vencimiento))
    return Contenedor(
        reloj=reloj, auditoria=auditoria, identidad=identidad, pacientes=modulo_pacientes,
        inferencia=inferencia, casos=modulo_casos, validacion=validacion,
        informes=modulo_informes, notificaciones=notificaciones, verificador=verificador,
        verificador_tareas=verificador_tareas, almacen=almacen, es_local=es_local,
    )


def construir_local(config: Configuracion) -> Contenedor:
    """Todo en memoria, con tokens de desarrollo y fotos en una carpeta local."""
    from .infraestructura.modelo import desde_directorio

    directorio = Path(config.modelo_uri) if config.modelo_uri else ARTEFACTO_LOCAL
    return ensamblar(
        usuarios=memoria.RepoUsuariosMemoria(), pacientes=memoria.RepoPacientesMemoria(),
        casos=memoria.RepoCasosMemoria(), validaciones=memoria.RepoValidacionesMemoria(),
        informes=memoria.RepoInformesMemoria(),
        registro=RegistroAuditoriaConLogging(memoria.RegistroAuditoriaMemoria()),
        almacen=memoria.AlmacenLocal(config.carpeta_local, config.url_base),
        cuentas=memoria.CuentasMemoria(), push=memoria.PushMemoria(),
        cargar_artefacto=desde_directorio(directorio),
        verificador=memoria.VerificadorDesarrollo(),
        verificador_tareas=memoria.VerificadorTareasDesarrollo(),
        hilos_inferencia=config.hilos_inferencia, horas_vencimiento=config.horas_vencimiento,
        es_local=True,
    )


def construir_nube(config: Configuracion) -> Contenedor:
    from google.cloud import firestore

    from .infraestructura import firebase
    from .infraestructura import firestore as repos
    from .infraestructura.gcs import AlmacenGCS
    from .infraestructura.modelo import desde_gcs

    assert config.bucket_imagenes and config.modelo_uri and config.modelo_version
    assert config.tareas_audiencia and config.tareas_cuenta
    app = firebase.iniciar_app(config.proyecto)
    db = firestore.Client(project=config.proyecto)
    db_validaciones = firestore.Client(project=config.proyecto, database=config.base_validaciones)
    return ensamblar(
        usuarios=repos.RepoUsuariosFirestore(db), pacientes=repos.RepoPacientesFirestore(db),
        casos=repos.RepoCasosFirestore(db),
        validaciones=repos.RepoValidacionesFirestore(db_validaciones),
        informes=repos.RepoInformesFirestore(db),
        registro=RegistroAuditoriaConLogging(repos.RegistroAuditoriaFirestore(db)),
        almacen=AlmacenGCS(config.bucket_imagenes),
        cuentas=firebase.CuentasFirebase(app), push=firebase.PushFCM(app),
        cargar_artefacto=desde_gcs(config.modelo_uri, config.modelo_version),
        verificador=firebase.VerificadorFirebase(app),
        verificador_tareas=firebase.VerificadorTareasOIDC(config.tareas_audiencia,
                                                          config.tareas_cuenta),
        hilos_inferencia=config.hilos_inferencia, horas_vencimiento=config.horas_vencimiento,
    )


def construir(config: Configuracion) -> Contenedor:
    return construir_local(config) if config.es_local else construir_nube(config)
