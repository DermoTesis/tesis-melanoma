"""Módulo Gestión de Casos: registro, carga de fotos, envío a análisis y estados del caso.

Solo este módulo cambia el estado de un caso, y siempre con `exigir_transicion` dentro de una
actualización atómica del repositorio, así que ninguna operación puede saltarse un estado.
Validación Clínica e Informes piden los cambios a VALIDADO y CERRADO por su interfaz pública.

La inferencia es síncrona: `enviar` (POST /cases/{id}/submit) clasifica las dos fotos dentro de
la misma solicitud. Si falla, el caso queda en ERROR_ANALISIS y lo reprocesa la tarea periódica
de Cloud Scheduler (`reprocesar`), que también recupera los análisis que quedaron a medias.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime, timedelta

from .auditoria import ModuloAuditoria
from .errores import (
    DatosInvalidos, ErrorDominio, EstadoInvalido, ImagenInvalida, NoEncontrado,
)
from .inferencia import ModuloInferencia
from .modelos import (
    Caso, DatosClinicos, EstadoCaso, NotaInterna, TipoEvento, Usuario, Vista, exigir_transicion,
)
from .pacientes import ModuloPacientes
from .puertos import Almacen, GeneradorIds, Reloj, RepoCasos
from .sugerencias import sugerencia_por_defecto

log = logging.getLogger(__name__)

TIPOS_IMAGEN = frozenset({"image/jpeg", "image/png"})
MAX_BYTES_IMAGEN = 20 * 1024 * 1024
MAX_CARACTERES_TEXTO = 4000


def ruta_imagen(id_caso: str, vista: Vista) -> str:
    return f"casos/{id_caso}/{vista.value}"


class _YaEnCurso(Exception):
    """Otro proceso ya empezó o terminó el análisis de este caso."""


class ModuloCasos:
    def __init__(self, casos: RepoCasos, pacientes: ModuloPacientes, inferencia: ModuloInferencia,
                 almacen: Almacen, auditoria: ModuloAuditoria, reloj: Reloj,
                 generar_id: GeneradorIds, *, vigencia_urls: timedelta = timedelta(minutes=15),
                 analisis_colgado: timedelta = timedelta(minutes=10),
                 max_intentos_automaticos: int = 5):
        self._casos = casos
        self._pacientes = pacientes
        self._inferencia = inferencia
        self._almacen = almacen
        self._auditoria = auditoria
        self._reloj = reloj
        self._generar_id = generar_id
        self._vigencia_urls = vigencia_urls
        self._analisis_colgado = analisis_colgado
        self._max_intentos = max_intentos_automaticos

    # --- Consultas ---

    def obtener(self, medico: Usuario, id_caso: str) -> Caso:
        """Caso del médico que lo registró. A otro médico se le responde como si no existiera."""
        caso = self._casos.obtener(id_caso)
        if caso is None or caso.uid_medico != medico.uid:
            raise NoEncontrado("No se encontró el caso.")
        return caso

    def listar_mios(self, medico: Usuario) -> list[Caso]:
        return sorted(self._casos.listar_por_medico(medico.uid),
                      key=lambda c: c.fecha_creacion, reverse=True)

    def pendientes(self, medico: Usuario) -> list[Caso]:
        """Cola de validación priorizada por la probabilidad preliminar (RF-06.2, HU30)."""
        casos = [c for c in self._casos.listar_por_medico(medico.uid)
                 if c.estado == EstadoCaso.PENDIENTE_VALIDACION]
        return sorted(casos, key=lambda c: (
            -(c.prediccion.probabilidad_malignidad if c.prediccion else 0.0), c.fecha_creacion))

    def listar_por_paciente(self, medico: Usuario, id_paciente: str) -> list[Caso]:
        return sorted((c for c in self._casos.listar_por_paciente(id_paciente)
                       if c.uid_medico == medico.uid),
                      key=lambda c: c.fecha_creacion, reverse=True)

    def urls_imagenes(self, caso: Caso) -> dict[str, str]:
        return {vista: self._almacen.url_lectura(ruta, self._vigencia_urls)
                for vista, ruta in caso.imagenes.items()}

    # --- Registro y envío ---

    def registrar(self, medico: Usuario, id_paciente: str, datos: DatosClinicos,
                  id_solicitud: str | None = None) -> Caso:
        if id_solicitud:
            previo = self._casos.buscar_por_solicitud(medico.uid, id_solicitud)
            if previo is not None:
                return previo  # reenvío desde la cola offline de la app (RNF-08)
        self._pacientes.exigir_consentimiento(id_paciente)
        datos = replace(datos, ubicacion_lesion=" ".join(datos.ubicacion_lesion.split()))
        if not datos.ubicacion_lesion:
            raise DatosInvalidos("Indica la ubicación de la lesión.")
        caso = Caso(
            id=self._generar_id(),
            id_paciente=id_paciente,
            uid_medico=medico.uid,
            estado=EstadoCaso.REGISTRADO,
            datos_clinicos=replace(datos, sintomas=tuple(dict.fromkeys(datos.sintomas))),
            fecha_creacion=self._reloj.ahora(),
            id_solicitud=id_solicitud or None,
        )
        self._casos.crear(caso)
        self._auditoria.registrar(TipoEvento.REGISTRO_CASO, caso.id, medico)
        return caso

    def url_subida(self, medico: Usuario, id_caso: str, vista: Vista,
                   tipo_contenido: str) -> tuple[str, str, datetime]:
        """URL firmada para que la app cargue una foto directo en Cloud Storage."""
        caso = self.obtener(medico, id_caso)
        if caso.estado not in (EstadoCaso.REGISTRADO, EstadoCaso.ERROR_ANALISIS):
            raise EstadoInvalido(
                "Las fotos solo se pueden cargar antes de que el caso tenga su predicción.")
        if tipo_contenido not in TIPOS_IMAGEN:
            raise DatosInvalidos("Las fotos deben ser JPG o PNG.")
        ruta = ruta_imagen(id_caso, vista)
        url = self._almacen.url_subida(ruta, tipo_contenido, self._vigencia_urls)
        return url, ruta, self._reloj.ahora() + self._vigencia_urls

    def enviar(self, medico: Usuario, id_caso: str) -> Caso:
        """Envía el caso a análisis y devuelve el caso con su predicción o en ERROR_ANALISIS.

        Es idempotente: si el caso ya se envió (reenvío de la cola offline), lo devuelve tal cual.
        """
        caso = self.obtener(medico, id_caso)
        if caso.estado not in (EstadoCaso.REGISTRADO, EstadoCaso.ERROR_ANALISIS):
            return caso
        return self._analizar(caso, {EstadoCaso.REGISTRADO, EstadoCaso.ERROR_ANALISIS})

    def reprocesar(self) -> dict[str, int]:
        """Tarea de Cloud Scheduler: reintenta los análisis fallidos o que quedaron a medias."""
        ahora = self._reloj.ahora()
        candidatos = [
            c for c in self._casos.listar_por_estado(EstadoCaso.ERROR_ANALISIS)
            if c.intentos_analisis < self._max_intentos
        ] + [
            c for c in self._casos.listar_por_estado(EstadoCaso.EN_ANALISIS)
            if self._colgado(c, ahora)
        ]
        resumen = {"candidatos": len(candidatos), "con_prediccion": 0, "con_error": 0}
        for caso in candidatos:
            try:
                resultado = self._analizar(
                    caso, {EstadoCaso.ERROR_ANALISIS, EstadoCaso.EN_ANALISIS})
            except ErrorDominio as error:
                log.warning("No se reprocesó el caso %s: %s", caso.id, error.mensaje)
                continue
            if resultado.estado == EstadoCaso.PENDIENTE_VALIDACION:
                resumen["con_prediccion"] += 1
            elif resultado.estado == EstadoCaso.ERROR_ANALISIS:
                resumen["con_error"] += 1
        return resumen

    def _colgado(self, caso: Caso, ahora: datetime) -> bool:
        return (caso.estado == EstadoCaso.EN_ANALISIS and caso.fecha_inicio_analisis is not None
                and ahora - caso.fecha_inicio_analisis >= self._analisis_colgado)

    def _leer_fotos(self, id_caso: str) -> dict[Vista, bytes]:
        fotos = {vista: self._almacen.leer(ruta_imagen(id_caso, vista)) for vista in Vista}
        if any(datos is None for datos in fotos.values()):
            raise DatosInvalidos("Faltan fotos del caso: carga las dos antes de enviarlo.")
        if any(len(datos) > MAX_BYTES_IMAGEN for datos in fotos.values() if datos):
            raise ImagenInvalida("Una de las fotos supera los 20 MB. Vuelve a cargarla.")
        return fotos  # type: ignore[return-value]

    def _analizar(self, caso: Caso, desde: set[EstadoCaso]) -> Caso:
        # El paciente pudo revocar su consentimiento después de registrar el caso.
        self._pacientes.exigir_consentimiento(caso.id_paciente)
        fotos = self._leer_fotos(caso.id)
        ahora = self._reloj.ahora()

        def iniciar(actual: Caso) -> Caso:
            reintento_colgado = EstadoCaso.EN_ANALISIS in desde and self._colgado(actual, ahora)
            if actual.estado == EstadoCaso.EN_ANALISIS and not reintento_colgado:
                raise _YaEnCurso
            if actual.estado not in desde:
                raise _YaEnCurso
            exigir_transicion(actual.estado, EstadoCaso.EN_ANALISIS)
            return replace(
                actual,
                estado=EstadoCaso.EN_ANALISIS,
                intentos_analisis=actual.intentos_analisis + 1,
                fecha_inicio_analisis=ahora,
                imagenes={vista.value: ruta_imagen(actual.id, vista) for vista in Vista},
                ultimo_error=None,
            )

        try:
            caso = self._casos.actualizar(caso.id, iniciar)
        except _YaEnCurso:
            return self._casos.obtener(caso.id) or caso

        try:
            prediccion = self._inferencia.predecir(fotos[Vista.A], fotos[Vista.B])
        except Exception as error:
            mensaje = (error.mensaje if isinstance(error, ErrorDominio)
                       else "No se pudo completar el análisis. Se reintentará automáticamente.")
            log.exception("Falló el análisis del caso %s", caso.id)

            def fallar(actual: Caso) -> Caso:
                exigir_transicion(actual.estado, EstadoCaso.ERROR_ANALISIS)
                return replace(actual, estado=EstadoCaso.ERROR_ANALISIS, ultimo_error=mensaje)

            try:
                caso = self._casos.actualizar(caso.id, fallar)
            except EstadoInvalido:  # otro reintento terminó antes
                return self._casos.obtener(caso.id) or caso
            self._auditoria.registrar(TipoEvento.ERROR_ANALISIS, caso.id,
                                      intento=caso.intentos_analisis,
                                      error=type(error).__name__)
            return caso

        def completar(actual: Caso) -> Caso:
            exigir_transicion(actual.estado, EstadoCaso.PENDIENTE_VALIDACION)
            return replace(actual, estado=EstadoCaso.PENDIENTE_VALIDACION, prediccion=prediccion,
                           sugerencia_examenes=sugerencia_por_defecto(prediccion))

        try:
            caso = self._casos.actualizar(caso.id, completar)
        except EstadoInvalido:
            return self._casos.obtener(caso.id) or caso
        self._auditoria.registrar(
            TipoEvento.PREDICCION, caso.id,
            version_modelo=prediccion.version_modelo,
            clase_predicha=prediccion.clase_predicha.value,
            probabilidad_malignidad=prediccion.probabilidad_malignidad,
            salida_modelo=prediccion.salida_modelo,
            latencia_ms=prediccion.latencia_ms,
        )
        return caso

    # --- Apoyo a la decisión (RF-06.1, RF-06.3) ---

    def actualizar_sugerencia(self, medico: Usuario, id_caso: str, texto: str) -> Caso:
        self.obtener(medico, id_caso)
        texto = texto.strip()[:MAX_CARACTERES_TEXTO]

        def cambio(actual: Caso) -> Caso:
            if actual.estado != EstadoCaso.PENDIENTE_VALIDACION:
                raise EstadoInvalido(
                    "La sugerencia de exámenes solo se edita antes de validar el caso.")
            return replace(actual, sugerencia_examenes=texto or None)

        return self._casos.actualizar(id_caso, cambio)

    def agregar_nota(self, medico: Usuario, id_caso: str, texto: str) -> Caso:
        self.obtener(medico, id_caso)
        texto = texto.strip()
        if not texto:
            raise DatosInvalidos("La observación está vacía.")
        if len(texto) > MAX_CARACTERES_TEXTO:
            raise DatosInvalidos("La observación es demasiado larga.")
        nota = NotaInterna(texto=texto, uid_autor=medico.uid, autor_nombre=medico.nombres,
                           fecha=self._reloj.ahora())
        return self._casos.actualizar(
            id_caso, lambda actual: replace(actual, notas_internas=actual.notas_internas + (nota,)))

    # --- Interfaz para Validación Clínica, Informes y Notificaciones ---

    def obtener_interno(self, id_caso: str) -> Caso:
        caso = self._casos.obtener(id_caso)
        if caso is None:
            raise NoEncontrado("No se encontró el caso.")
        return caso

    def casos_del_paciente(self, id_paciente: str) -> list[Caso]:
        """Todos los casos del paciente, de cualquier médico (para el historial de informes)."""
        return self._casos.listar_por_paciente(id_paciente)

    def marcar_validado(self, id_caso: str) -> Caso:
        def cambio(actual: Caso) -> Caso:
            if actual.estado == EstadoCaso.VALIDADO:
                return actual
            exigir_transicion(actual.estado, EstadoCaso.VALIDADO)
            return replace(actual, estado=EstadoCaso.VALIDADO)

        return self._casos.actualizar(id_caso, cambio)

    def marcar_cerrado(self, id_caso: str) -> Caso:
        def cambio(actual: Caso) -> Caso:
            exigir_transicion(actual.estado, EstadoCaso.CERRADO)
            return replace(actual, estado=EstadoCaso.CERRADO)

        return self._casos.actualizar(id_caso, cambio)

    def vencidos(self, limite: timedelta) -> list[Caso]:
        """Casos pendientes de validación desde hace más de `limite` y aún sin alerta (RF-04.5)."""
        corte = self._reloj.ahora() - limite
        return [c for c in self._casos.listar_por_estado(EstadoCaso.PENDIENTE_VALIDACION)
                if c.fecha_alerta_vencido is None and c.prediccion is not None
                and c.prediccion.fecha_inferencia <= corte]

    def marcar_alertado(self, id_caso: str) -> Caso:
        ahora = self._reloj.ahora()
        return self._casos.actualizar(
            id_caso, lambda actual: replace(actual, fecha_alerta_vencido=ahora))
