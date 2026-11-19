"""Módulo Validación Clínica: la decisión del especialista, con sustento, en un registro inmutable.

Las validaciones viven en una base de datos de Firestore aparte, de solo inserción (Tabla 5 de la
memoria). La primera validación de un caso usa un id fijo (`<id_caso>-principal`), así que dos
envíos simultáneos no pueden crear dos validaciones principales: el segundo choca con el
primero. Una validación posterior es complementaria (`complementa_de`) y nunca edita la anterior.

Primero se inserta la validación y después el caso pasa a VALIDADO. Si el proceso se corta entre
ambos pasos, el siguiente intento detecta la validación existente y completa la transición.
"""

from __future__ import annotations

from .auditoria import ModuloAuditoria
from .casos import MAX_CARACTERES_TEXTO, ModuloCasos
from .errores import Conflicto, DatosInvalidos, EstadoInvalido
from .modelos import ClaseLesion, Decision, EstadoCaso, TipoEvento, Usuario, Validacion
from .puertos import GeneradorIds, Reloj, RepoValidaciones


def id_validacion_principal(id_caso: str) -> str:
    return f"{id_caso}-principal"


class ModuloValidacion:
    def __init__(self, validaciones: RepoValidaciones, casos: ModuloCasos,
                 auditoria: ModuloAuditoria, reloj: Reloj, generar_id: GeneradorIds):
        self._validaciones = validaciones
        self._casos = casos
        self._auditoria = auditoria
        self._reloj = reloj
        self._generar_id = generar_id

    def registrar(self, medico: Usuario, *, id_caso: str, decision: Decision,
                  sustento_clinico: str, clase_final: ClaseLesion | None = None,
                  examenes_adicionales: str | None = None,
                  sugerencia_tomada: bool | None = None,
                  complementa_de: str | None = None) -> Validacion:
        caso = self._casos.obtener(medico, id_caso)
        prediccion = caso.prediccion
        if prediccion is None:
            raise EstadoInvalido(
                "La validación no está disponible hasta que termine la predicción preliminar.")
        sustento = sustento_clinico.strip()
        if not sustento:
            raise DatosInvalidos("El sustento clínico es obligatorio para guardar la validación.")
        if len(sustento) > MAX_CARACTERES_TEXTO:
            raise DatosInvalidos("El sustento clínico es demasiado largo.")

        existentes = self._validaciones.listar_por_caso(id_caso)
        if complementa_de is None:
            if existentes:
                self._reparar_estado(id_caso)
                raise Conflicto(
                    "El caso ya tiene una validación. Registra una validación complementaria.")
            if caso.estado != EstadoCaso.PENDIENTE_VALIDACION:
                raise EstadoInvalido("El caso no está pendiente de validación.")
            id_validacion = id_validacion_principal(id_caso)
        else:
            if not any(v.id == complementa_de for v in existentes):
                raise DatosInvalidos("La validación a complementar no existe.")
            id_validacion = self._generar_id()

        if decision == Decision.CONFIRMAR:
            final: ClaseLesion | None = prediccion.clase_predicha
        elif decision == Decision.CORREGIR:
            if clase_final is None or clase_final == prediccion.clase_predicha:
                raise DatosInvalidos(
                    "Para corregir, selecciona una clasificación distinta a la predicción.")
            final = clase_final
        else:
            final = None

        examenes = (examenes_adicionales or "").strip() or caso.sugerencia_examenes
        validacion = Validacion(
            id=id_validacion,
            id_caso=id_caso,
            uid_especialista=medico.uid,
            especialista_nombre=medico.nombres,
            numero_colegiatura=medico.numero_colegiatura or "",
            decision=decision,
            clase_final=final,
            sustento_clinico=sustento,
            fecha_validacion=self._reloj.ahora(),
            prediccion_original=prediccion,
            examenes_adicionales=examenes[:MAX_CARACTERES_TEXTO] if examenes else None,
            sugerencia_tomada=sugerencia_tomada,
            complementa_de=complementa_de,
        )
        try:
            self._validaciones.insertar(validacion)
        except Conflicto:
            self._reparar_estado(id_caso)
            raise Conflicto(
                "El caso ya tiene una validación. Registra una validación complementaria."
            ) from None
        if complementa_de is None:
            self._casos.marcar_validado(id_caso)
        self._auditoria.registrar(
            TipoEvento.VALIDACION, id_caso, medico,
            decision=decision.value,
            complementaria=complementa_de is not None,
            # Monitoreo del modelo (RF-03.6, RNF-14): concordancia por versión.
            version_modelo=prediccion.version_modelo,
            clase_predicha=prediccion.clase_predicha.value,
            clase_final=final.value if final else None,
            concordante=validacion.concordante,
        )
        return validacion

    def _reparar_estado(self, id_caso: str) -> None:
        caso = self._casos.obtener_interno(id_caso)
        if caso.estado == EstadoCaso.PENDIENTE_VALIDACION:
            self._casos.marcar_validado(id_caso)

    def listar(self, medico: Usuario, id_caso: str) -> list[Validacion]:
        self._casos.obtener(medico, id_caso)
        return self._validaciones.listar_por_caso(id_caso)

    def ultima(self, id_caso: str) -> Validacion | None:
        """Interfaz para Informes: la validación vigente del caso (la más reciente)."""
        validaciones = self._validaciones.listar_por_caso(id_caso)
        return max(validaciones, key=lambda v: v.fecha_validacion) if validaciones else None
