"""Módulo Informes: cierre condicionado del caso, conducta clínica e informe exportable.

El cierre solo procede si Validación Clínica entrega una validación registrada y el caso está en
VALIDADO (RF-07.1, RF-05.2). El informe lleva la conclusión validada por el especialista y el
alcance de apoyo diagnóstico (RF-05.3) y la constancia de que el caso se evaluó con apoyo de la
herramienta, con la versión del modelo (D5 en `app/PENDIENTES.md`); nunca la predicción
preliminar sin validar ni las observaciones internas (RF-05.5, RF-06.3).

Un informe cerrado forma parte del expediente del paciente, así que lo puede consultar cualquier
especialista habilitado (historial, RF-05.6). Los casos abiertos solo los ve quien los registró.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .auditoria import ModuloAuditoria
from .casos import MAX_CARACTERES_TEXTO, ModuloCasos
from .errores import DatosInvalidos, NoEncontrado, ValidacionRequerida
from .identidad import ModuloIdentidad
from .modelos import ClaseLesion, EstadoCaso, Informe, TipoEvento, Usuario, Validacion
from .pacientes import ModuloPacientes
from .puertos import Reloj, RepoInformes
from .validacion import ModuloValidacion

ALCANCE = (
    "Herramienta de apoyo diagnóstico. No reemplaza el criterio médico ni los exámenes "
    "clínicos pertinentes."
)


def constancia_herramienta(version_modelo: str) -> str:
    """Mismo texto que `toolUsageNotice` de la app."""
    return (
        f"Caso evaluado con apoyo de Dermavía (versión {version_modelo}), herramienta de apoyo "
        "diagnóstico para melanoma. Su predicción preliminar fue revisada por el especialista, "
        "a quien corresponde la conclusión."
    )


def conclusion(validacion: Validacion) -> str:
    if validacion.clase_final is None:
        return "Predicción preliminar descartada; se requiere evaluación clínica."
    if validacion.clase_final == ClaseLesion.MELANOMA:
        return "Lesión compatible con melanoma."
    return "Lesión no compatible con melanoma."


@dataclass(frozen=True)
class DocumentoInforme:
    """Contenido exportable del informe (lo que la app imprime o comparte en PDF)."""

    id_informe: str
    id_caso: str
    fecha_cierre: datetime
    paciente_nombres: str
    numero_historia_clinica: str
    fecha_nacimiento: date
    ubicacion_lesion: str
    conclusion: str
    decision: str
    sustento_clinico: str
    examenes_adicionales: str | None
    conducta_clinica: str
    especialista_nombre: str
    numero_colegiatura: str
    establecimiento: str
    alcance: str
    constancia_herramienta: str


class ModuloInformes:
    def __init__(self, informes: RepoInformes, casos: ModuloCasos,
                 validacion: ModuloValidacion, pacientes: ModuloPacientes,
                 identidad: ModuloIdentidad, auditoria: ModuloAuditoria, reloj: Reloj):
        self._informes = informes
        self._casos = casos
        self._validacion = validacion
        self._pacientes = pacientes
        self._identidad = identidad
        self._auditoria = auditoria
        self._reloj = reloj

    def cerrar(self, medico: Usuario, id_caso: str, conducta_clinica: str) -> Informe:
        caso = self._casos.obtener(medico, id_caso)
        validacion = self._validacion.ultima(id_caso)
        # Barrera de RF-07.1: sin validación registrada no hay cierre ni informe.
        if validacion is None or caso.estado != EstadoCaso.VALIDADO:
            raise ValidacionRequerida()
        conducta = conducta_clinica.strip()
        if not conducta:
            raise DatosInvalidos("Registra la conducta o recomendación clínica.")
        if len(conducta) > MAX_CARACTERES_TEXTO:
            raise DatosInvalidos("La conducta clínica es demasiado larga.")
        informe = Informe(
            id=id_caso,  # un informe por caso: un segundo cierre choca con el primero
            id_caso=id_caso,
            id_validacion=validacion.id,
            uid_medico=medico.uid,
            conducta_clinica=conducta,
            fecha_cierre=self._reloj.ahora(),
        )
        self._informes.insertar(informe)
        self._casos.marcar_cerrado(id_caso)
        self._auditoria.registrar(TipoEvento.CIERRE_CASO, id_caso, medico)
        return informe

    def documento(self, id_caso: str) -> DocumentoInforme:
        caso = self._casos.obtener_interno(id_caso)
        informe = self._informes.obtener_por_caso(id_caso)
        if informe is None or caso.estado != EstadoCaso.CERRADO:
            raise ValidacionRequerida()
        validacion = self._validacion.ultima(id_caso)
        if validacion is None:
            raise ValidacionRequerida()
        paciente = self._pacientes.obtener(caso.id_paciente)
        especialista = self._identidad.obtener(validacion.uid_especialista)
        return DocumentoInforme(
            id_informe=informe.id,
            id_caso=id_caso,
            fecha_cierre=informe.fecha_cierre,
            paciente_nombres=paciente.nombres,
            numero_historia_clinica=paciente.numero_historia_clinica,
            fecha_nacimiento=paciente.fecha_nacimiento,
            ubicacion_lesion=caso.datos_clinicos.ubicacion_lesion,
            conclusion=conclusion(validacion),
            decision=validacion.decision.value,
            sustento_clinico=validacion.sustento_clinico,
            examenes_adicionales=validacion.examenes_adicionales,
            conducta_clinica=informe.conducta_clinica,
            especialista_nombre=validacion.especialista_nombre,
            numero_colegiatura=validacion.numero_colegiatura,
            establecimiento=especialista.establecimiento if especialista else "",
            alcance=ALCANCE,
            constancia_herramienta=constancia_herramienta(
                validacion.prediccion_original.version_modelo),
        )

    def historial(self, id_paciente: str) -> list[DocumentoInforme]:
        """Casos cerrados del paciente, en orden cronológico (RF-05.6, HU28)."""
        self._pacientes.obtener(id_paciente)
        documentos = []
        # Los informes cerrados son parte del expediente: se listan los de todos los médicos.
        for caso in self._casos.casos_del_paciente(id_paciente):
            if caso.estado == EstadoCaso.CERRADO:
                try:
                    documentos.append(self.documento(caso.id))
                except (ValidacionRequerida, NoEncontrado):
                    continue
        return sorted(documentos, key=lambda d: d.fecha_cierre)
