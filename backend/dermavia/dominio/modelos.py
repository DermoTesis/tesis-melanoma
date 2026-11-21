"""Entidades del dominio y la secuencia obligatoria de estados del caso.

Los nombres de los campos siguen el esquema de Firestore de la memoria (sección 5.2.2.2). Las
entidades son inmutables: un cambio produce una copia (`dataclasses.replace`), y solo los
repositorios la persisten, de forma atómica.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

from .errores import EstadoInvalido


class Rol(StrEnum):
    ESPECIALISTA = "especialista"
    ADMIN = "admin"


class EstadoCuenta(StrEnum):
    PENDIENTE_ACTIVACION = "PENDIENTE_ACTIVACION"
    ACTIVO = "ACTIVO"


class EstadoCaso(StrEnum):
    REGISTRADO = "REGISTRADO"
    EN_ANALISIS = "EN_ANALISIS"
    ERROR_ANALISIS = "ERROR_ANALISIS"
    PENDIENTE_VALIDACION = "PENDIENTE_VALIDACION"
    VALIDADO = "VALIDADO"
    CERRADO = "CERRADO"


# REGISTRADO → EN_ANALISIS → (ERROR_ANALISIS) → PENDIENTE_VALIDACION → VALIDADO → CERRADO.
# No hay ninguna transición que llegue a CERRADO sin pasar por VALIDADO (RF-07.1).
# EN_ANALISIS → EN_ANALISIS es el reintento de un análisis que quedó a medias (la instancia de
# Cloud Run se apagó durante la solicitud); lo hace la tarea periódica.
TRANSICIONES: dict[EstadoCaso, frozenset[EstadoCaso]] = {
    EstadoCaso.REGISTRADO: frozenset({EstadoCaso.EN_ANALISIS}),
    EstadoCaso.EN_ANALISIS: frozenset({
        EstadoCaso.PENDIENTE_VALIDACION, EstadoCaso.ERROR_ANALISIS, EstadoCaso.EN_ANALISIS}),
    EstadoCaso.ERROR_ANALISIS: frozenset({EstadoCaso.EN_ANALISIS}),
    EstadoCaso.PENDIENTE_VALIDACION: frozenset({EstadoCaso.VALIDADO}),
    EstadoCaso.VALIDADO: frozenset({EstadoCaso.CERRADO}),
    EstadoCaso.CERRADO: frozenset(),
}


def exigir_transicion(desde: EstadoCaso, hacia: EstadoCaso) -> None:
    if hacia not in TRANSICIONES[desde]:
        raise EstadoInvalido(f"El caso está en {desde.value} y no puede pasar a {hacia.value}.")


class Vista(StrEnum):
    """Las dos fotos dermatoscópicas del caso, en el orden de las entradas del modelo.

    El modelo es simétrico (se entrenó con pares al azar), así que el orden no cambia la
    predicción de forma sistemática. La segunda foto es la misma lesión tras retirar el
    dermatoscopio y volver a apoyarlo con otro ángulo o posición (D1 en `app/PENDIENTES.md`);
    los nombres son neutros porque ninguna de las dos tiene un papel distinto.
    """

    A = "a"
    B = "b"


class ClaseLesion(StrEnum):
    """Melanoma frente a todas las demás clases de HAM10000 (decisión del 2026-10-01)."""

    MELANOMA = "melanoma"
    NO_MELANOMA = "no_melanoma"


class Decision(StrEnum):
    CONFIRMAR = "confirmar"
    CORREGIR = "corregir"
    DESCARTAR = "descartar"


class Sexo(StrEnum):
    FEMENINO = "femenino"
    MASCULINO = "masculino"


class Fototipo(StrEnum):
    I = "I"  # noqa: E741
    II = "II"
    III = "III"
    IV = "IV"
    V = "V"
    VI = "VI"


class TiempoAparicion(StrEnum):
    MENOS_3_MESES = "menos_3_meses"
    ENTRE_3_Y_12_MESES = "entre_3_y_12_meses"
    MAS_DE_1_ANIO = "mas_de_1_anio"
    NO_SABE = "no_sabe"


class Sintoma(StrEnum):
    CAMBIO_TAMANO = "cambio_tamano"
    PICOR = "picor"
    SANGRADO = "sangrado"
    CAMBIO_COLOR = "cambio_color"
    DOLOR = "dolor"


@dataclass(frozen=True)
class Usuario:
    uid: str
    rol: Rol
    dni: str
    nombres: str
    correo: str
    estado: EstadoCuenta
    establecimiento: str
    acceso_clinico: bool = True
    numero_colegiatura: str | None = None
    colegiatura_verificada_por: str | None = None
    fecha_verificacion: datetime | None = None
    fecha_aceptacion_terminos: datetime | None = None
    tokens_dispositivo: tuple[str, ...] = ()

    @property
    def es_admin(self) -> bool:
        return self.rol == Rol.ADMIN

    @property
    def es_especialista(self) -> bool:
        return self.rol == Rol.ESPECIALISTA


@dataclass(frozen=True)
class Consentimiento:
    otorgado: bool
    fecha_otorgamiento: datetime
    uid_medico: str
    medico_nombre: str
    fecha_revocacion: datetime | None = None

    @property
    def vigente(self) -> bool:
        return self.otorgado and self.fecha_revocacion is None


@dataclass(frozen=True)
class Paciente:
    """El paciente no tiene cuenta de acceso: lo registra el médico especialista."""

    id: str
    numero_historia_clinica: str
    nombres: str
    fecha_nacimiento: date
    sexo: Sexo
    fototipo: Fototipo
    uid_medico_registro: str
    fecha_registro: datetime
    consentimiento: Consentimiento | None = None

    @property
    def consentimiento_vigente(self) -> bool:
        return self.consentimiento is not None and self.consentimiento.vigente


class ImpresionClinica(StrEnum):
    """Impresión del especialista antes de conocer la predicción (D4 en `app/PENDIENTES.md`).

    Se registra con el caso, antes del análisis, para que la predicción no la condicione: un
    consejo erróneo de la IA empeoró las decisiones de los médicos en experimentos de lectura
    (Tschandl et al., 2020, citado en el short paper, VI-C).
    """

    SOSPECHA_MELANOMA = "sospecha_melanoma"
    SIN_SOSPECHA = "sin_sospecha"
    DUDOSA = "dudosa"


@dataclass(frozen=True)
class DatosClinicos:
    ubicacion_lesion: str
    tiempo_aparicion: TiempoAparicion
    sintomas: tuple[Sintoma, ...] = ()
    # Obligatoria al registrar un caso; nula solo en casos registrados antes de D4.
    impresion_clinica: ImpresionClinica | None = None


@dataclass(frozen=True)
class Prediccion:
    """Predicción preliminar del módulo Inferencia. Siempre la valida el médico.

    La clase se decide con la salida SIN calibrar del modelo (`salida_modelo >= umbral_operativo`),
    como en el registro de EXP-04. La probabilidad calibrada es la que se le muestra al médico, y
    `linea_alerta` es la calibración del umbral, solo para mostrar: por los escalones de la
    calibración isotónica, la misma probabilidad mostrada puede tener o no alerta, así que la app
    nunca debe deducir la clase comparando la probabilidad con la línea de alerta.
    """

    probabilidad_malignidad: float
    clase_predicha: ClaseLesion
    salida_modelo: float
    umbral_operativo: float
    linea_alerta: float
    version_modelo: str
    sha256_modelo: str
    fecha_inferencia: datetime
    latencia_ms: float


@dataclass(frozen=True)
class NotaInterna:
    """Observación clínica interna (RF-06.3): nunca sale en el informe exportable."""

    texto: str
    uid_autor: str
    autor_nombre: str
    fecha: datetime


@dataclass(frozen=True)
class Caso:
    id: str
    id_paciente: str
    uid_medico: str
    estado: EstadoCaso
    datos_clinicos: DatosClinicos
    fecha_creacion: datetime
    # Rutas en Cloud Storage de las fotos ya cargadas, por vista ("a", "b").
    imagenes: dict[str, str] = field(default_factory=dict)
    prediccion: Prediccion | None = None
    sugerencia_examenes: str | None = None
    notas_internas: tuple[NotaInterna, ...] = ()
    intentos_analisis: int = 0
    fecha_inicio_analisis: datetime | None = None
    ultimo_error: str | None = None
    fecha_alerta_vencido: datetime | None = None
    # Clave que manda la app con cada caso de su cola offline, para que un reenvío no lo duplique.
    id_solicitud: str | None = None


@dataclass(frozen=True)
class Validacion:
    """Registro inmutable de la decisión del especialista (RF-04.4): solo se inserta."""

    id: str
    id_caso: str
    uid_especialista: str
    especialista_nombre: str
    numero_colegiatura: str
    decision: Decision
    clase_final: ClaseLesion | None  # None si descarta la predicción
    sustento_clinico: str
    fecha_validacion: datetime
    prediccion_original: Prediccion
    examenes_adicionales: str | None = None
    sugerencia_tomada: bool | None = None
    complementa_de: str | None = None

    @property
    def concordante(self) -> bool:
        """Para el monitoreo del modelo (RF-03.6, RNF-14): el especialista confirmó la clase."""
        return self.clase_final == self.prediccion_original.clase_predicha


@dataclass(frozen=True)
class Informe:
    id: str
    id_caso: str
    id_validacion: str
    uid_medico: str
    conducta_clinica: str
    fecha_cierre: datetime
    url_pdf: str | None = None


class TipoEvento(StrEnum):
    ALTA_CUENTA = "alta_cuenta"
    ACTIVACION_CUENTA = "activacion_cuenta"
    ACEPTACION_ALCANCE = "aceptacion_alcance"
    CAMBIO_PERMISOS = "cambio_permisos"
    REGISTRO_PACIENTE = "registro_paciente"
    CONSENTIMIENTO = "consentimiento"
    REVOCACION_CONSENTIMIENTO = "revocacion_consentimiento"
    REGISTRO_CASO = "registro_caso"
    PREDICCION = "prediccion"
    ERROR_ANALISIS = "error_analisis"
    VALIDACION = "validacion"
    CIERRE_CASO = "cierre_caso"
    ALERTA_VENCIDO = "alerta_vencido"


@dataclass(frozen=True)
class EventoAuditoria:
    id: str
    tipo: TipoEvento
    referencia: str
    uid_actor: str | None
    actor_nombre: str
    fecha: datetime
    detalle: dict[str, object] = field(default_factory=dict)
