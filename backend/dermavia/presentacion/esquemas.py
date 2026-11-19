"""Contrato JSON de la API: lo que manda la app y lo que recibe.

FastAPI publica este contrato en `/docs` (OpenAPI), que es la referencia para los clientes REST
de la app (pendiente A9 de `app/PENDIENTES.md`). Las respuestas exponen solo lo necesario:

- la predicción trae la clase ya decidida (`clase_predicha`), la probabilidad calibrada, la
  línea de alerta (solo para mostrar) y la banda; no trae la salida sin calibrar ni el umbral,
  para que la app no tenga con qué recalcular la clase;
- el usuario no expone sus tokens de dispositivo;
- el informe no trae observaciones internas ni la predicción sin validar.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from ..dominio import sugerencias
from ..dominio.informes import DocumentoInforme
from ..dominio.modelos import (
    Caso, ClaseLesion, Decision, EstadoCaso, EstadoCuenta, Fototipo, Prediccion, Rol, Sexo,
    Sintoma, TiempoAparicion, TipoEvento, Vista,
)


class Modelo(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# --- Errores ---

class Error(BaseModel):
    codigo: str = Field(examples=["consent-required"])
    mensaje: str


class RespuestaError(BaseModel):
    error: Error


# --- Identidad ---

class UsuarioOut(Modelo):
    uid: str
    rol: Rol
    dni: str
    nombres: str
    correo: str
    estado: EstadoCuenta
    establecimiento: str
    acceso_clinico: bool
    numero_colegiatura: str | None
    fecha_verificacion: datetime | None
    fecha_aceptacion_terminos: datetime | None

    @computed_field
    @property
    def requiere_aceptar_alcance(self) -> bool:
        return self.rol == Rol.ESPECIALISTA and self.fecha_aceptacion_terminos is None


class AltaEspecialistaIn(Entrada):
    nombres: str = Field(min_length=1, max_length=120)
    correo: str = Field(min_length=3, max_length=120)
    dni: str = Field(min_length=8, max_length=8)
    numero_colegiatura: str = Field(min_length=3, max_length=6)
    colegiatura_verificada: bool
    establecimiento: str | None = Field(default=None, max_length=120)


class PermisosIn(Entrada):
    rol: Rol | None = None
    acceso_clinico: bool | None = None


class DispositivoIn(Entrada):
    token: str = Field(min_length=1, max_length=4096)


class EventoOut(Modelo):
    id: str
    tipo: TipoEvento
    referencia: str
    actor_nombre: str
    fecha: datetime


# --- Pacientes ---

class ConsentimientoOut(Modelo):
    otorgado: bool
    fecha_otorgamiento: datetime
    medico_nombre: str
    fecha_revocacion: datetime | None
    vigente: bool


class PacienteIn(Entrada):
    numero_historia_clinica: str = Field(min_length=1, max_length=40)
    nombres: str = Field(min_length=1, max_length=120)
    fecha_nacimiento: date
    sexo: Sexo
    fototipo: Fototipo


class PacienteOut(Modelo):
    id: str
    numero_historia_clinica: str
    nombres: str
    fecha_nacimiento: date
    sexo: Sexo
    fototipo: Fototipo
    uid_medico_registro: str
    fecha_registro: datetime
    consentimiento: ConsentimientoOut | None
    consentimiento_vigente: bool


# --- Casos ---

class DatosClinicosIn(Entrada):
    ubicacion_lesion: str = Field(min_length=1, max_length=200)
    tiempo_aparicion: TiempoAparicion
    sintomas: list[Sintoma] = Field(default_factory=list, max_length=len(Sintoma))


class DatosClinicosOut(Modelo):
    ubicacion_lesion: str
    tiempo_aparicion: TiempoAparicion
    sintomas: list[Sintoma]


class CasoIn(Entrada):
    id_paciente: str = Field(min_length=1, max_length=64)
    datos_clinicos: DatosClinicosIn
    id_solicitud: str | None = Field(
        default=None, max_length=64,
        description="Clave única que genera la app por caso; un reenvío con la misma clave "
                    "devuelve el caso ya registrado en vez de duplicarlo (cola offline).")


class PrediccionOut(BaseModel):
    probabilidad_malignidad: float = Field(description="Probabilidad calibrada que ve el médico.")
    clase_predicha: ClaseLesion = Field(
        description="Decidida por el backend. La app no debe recalcularla.")
    linea_alerta: float = Field(
        description="Solo para mostrar. No sirve para decidir la clase: por la calibración, la "
                    "misma probabilidad puede tener o no alerta.")
    banda: str = Field(examples=["sin_alerta", "baja", "ambigua", "alta"])
    version_modelo: str
    fecha_inferencia: datetime

    @classmethod
    def desde(cls, p: Prediccion) -> PrediccionOut:
        return cls(probabilidad_malignidad=p.probabilidad_malignidad,
                   clase_predicha=p.clase_predicha, linea_alerta=p.linea_alerta,
                   banda=sugerencias.banda(p), version_modelo=p.version_modelo,
                   fecha_inferencia=p.fecha_inferencia)


class NotaOut(Modelo):
    texto: str
    autor_nombre: str
    fecha: datetime


class CasoOut(BaseModel):
    id: str
    id_paciente: str
    estado: EstadoCaso
    datos_clinicos: DatosClinicosOut
    fecha_creacion: datetime
    vistas_cargadas: list[Vista]
    prediccion: PrediccionOut | None
    sugerencia_examenes: str | None
    notas_internas: list[NotaOut]
    intentos_analisis: int
    ultimo_error: str | None
    alerta_vencido: bool
    urls_imagenes: dict[str, str] | None = Field(
        default=None, description="URL firmadas de lectura (15 min); solo en el detalle.")

    @classmethod
    def desde(cls, c: Caso, urls_imagenes: dict[str, str] | None = None) -> CasoOut:
        return cls(
            id=c.id, id_paciente=c.id_paciente, estado=c.estado,
            datos_clinicos=DatosClinicosOut.model_validate(c.datos_clinicos),
            fecha_creacion=c.fecha_creacion,
            vistas_cargadas=[Vista(v) for v in sorted(c.imagenes)],
            prediccion=PrediccionOut.desde(c.prediccion) if c.prediccion else None,
            sugerencia_examenes=c.sugerencia_examenes,
            notas_internas=[NotaOut.model_validate(n) for n in c.notas_internas],
            intentos_analisis=c.intentos_analisis, ultimo_error=c.ultimo_error,
            alerta_vencido=c.fecha_alerta_vencido is not None, urls_imagenes=urls_imagenes,
        )


class EstadoCasoOut(BaseModel):
    id: str
    estado: EstadoCaso
    ultimo_error: str | None


class UrlSubidaIn(Entrada):
    vista: Vista
    tipo_contenido: str = Field(default="image/jpeg", examples=["image/jpeg", "image/png"])


class UrlSubidaOut(BaseModel):
    url: str
    metodo: str = "PUT"
    encabezados: dict[str, str]
    ruta: str
    vence: datetime


class TextoIn(Entrada):
    texto: str = Field(max_length=4000)


# --- Validación clínica ---

class ValidacionIn(Entrada):
    id_caso: str = Field(min_length=1, max_length=64)
    decision: Decision
    sustento_clinico: str = Field(max_length=4000)
    clase_final: ClaseLesion | None = Field(
        default=None, description="Obligatoria al corregir; se ignora al confirmar o descartar.")
    examenes_adicionales: str | None = Field(default=None, max_length=4000)
    sugerencia_tomada: bool | None = None
    complementa_de: str | None = Field(
        default=None, description="Id de la validación a complementar (nunca se edita una).")


class ValidacionOut(BaseModel):
    id: str
    id_caso: str
    especialista_nombre: str
    numero_colegiatura: str
    decision: Decision
    clase_final: ClaseLesion | None
    sustento_clinico: str
    fecha_validacion: datetime
    examenes_adicionales: str | None
    sugerencia_tomada: bool | None
    complementa_de: str | None
    prediccion_original: PrediccionOut


# --- Informes ---

class CierreIn(Entrada):
    conducta_clinica: str = Field(max_length=4000)


class InformeOut(Modelo):
    id: str
    id_caso: str
    id_validacion: str
    conducta_clinica: str
    fecha_cierre: datetime


class DocumentoInformeOut(Modelo):
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

    @classmethod
    def desde(cls, d: DocumentoInforme) -> DocumentoInformeOut:
        return cls.model_validate(d)


# --- Sistema y tareas ---

class SaludOut(BaseModel):
    estado: str
    version_modelo: str | None


class ResumenTareaOut(BaseModel):
    resumen: dict[str, int]
