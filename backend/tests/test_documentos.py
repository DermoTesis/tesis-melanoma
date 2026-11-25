"""Las entidades sobreviven la ida y vuelta a documentos de Firestore sin perder nada."""

from __future__ import annotations

from datetime import UTC, date, datetime

from dermavia.dominio.modelos import (
    Caso, ClaseLesion, Consentimiento, DatosClinicos, Decision, EstadoCaso, EstadoCuenta,
    EventoAuditoria, Fototipo, ImpresionClinica, Informe, NotaInterna, Paciente, Prediccion, Rol, Sexo, Sintoma,
    TiempoAparicion, TipoEvento, Usuario, Validacion,
)
from dermavia.infraestructura.documentos import a_documento, desde_documento

AHORA = datetime(2026, 11, 18, 15, 30, 12, 345000, tzinfo=UTC)
PREDICCION = Prediccion(
    probabilidad_malignidad=0.4375, clase_predicha=ClaseLesion.MELANOMA, salida_modelo=0.5,
    umbral_operativo=0.0137, linea_alerta=0.0699, version_modelo="v1", sha256_modelo="abc",
    fecha_inferencia=AHORA, latencia_ms=6.7)


def ida_y_vuelta(entidad):
    documento = a_documento(entidad)
    assert all(not isinstance(v, (tuple, date)) or isinstance(v, datetime)
               for v in documento.values())
    return desde_documento(type(entidad), documento)


def test_usuario():
    usuario = Usuario(uid="u1", rol=Rol.ESPECIALISTA, dni="12345678", nombres="Dra. A",
                      correo="a@b.pe", estado=EstadoCuenta.ACTIVO, establecimiento="H",
                      numero_colegiatura="123", fecha_aceptacion_terminos=AHORA,
                      tokens_dispositivo=("t1", "t2"))
    assert ida_y_vuelta(usuario) == usuario


def test_paciente_con_fecha_sin_hora():
    paciente = Paciente(id="p1", numero_historia_clinica="HC1", nombres="R", sexo=Sexo.FEMENINO,
                        fecha_nacimiento=date(1968, 4, 2), fototipo=Fototipo.IV,
                        uid_medico_registro="u1", fecha_registro=AHORA,
                        consentimiento=Consentimiento(True, AHORA, "u1", "Dra. A"))
    documento = a_documento(paciente)
    assert documento["fecha_nacimiento"] == datetime(1968, 4, 2, tzinfo=UTC)
    assert desde_documento(Paciente, documento) == paciente


def test_caso_completo():
    caso = Caso(id="c1", id_paciente="p1", uid_medico="u1", estado=EstadoCaso.PENDIENTE_VALIDACION,
                datos_clinicos=DatosClinicos("Espalda", TiempoAparicion.NO_SABE,
                                             (Sintoma.PICOR, Sintoma.DOLOR),
                                             ImpresionClinica.SOSPECHA_MELANOMA),
                fecha_creacion=AHORA, imagenes={"a": "casos/c1/a", "b": "casos/c1/b"},
                prediccion=PREDICCION, sugerencia_examenes="Biopsia",
                notas_internas=(NotaInterna("n", "u1", "Dra. A", AHORA),), intentos_analisis=1,
                id_solicitud="cola-1")
    assert ida_y_vuelta(caso) == caso


def test_caso_anterior_a_la_impresion_clinica():
    # Los casos registrados antes de D4 no tienen el campo en Firestore.
    documento = a_documento(DatosClinicos("Espalda", TiempoAparicion.NO_SABE))
    del documento["impresion_clinica"]
    assert desde_documento(DatosClinicos, documento).impresion_clinica is None


def test_validacion_informe_y_evento():
    validacion = Validacion(id="c1-principal", id_caso="c1", uid_especialista="u1",
                            especialista_nombre="Dra. A", numero_colegiatura="123",
                            decision=Decision.DESCARTAR, clase_final=None, sustento_clinico="s",
                            fecha_validacion=AHORA, prediccion_original=PREDICCION)
    informe = Informe(id="c1", id_caso="c1", id_validacion="c1-principal", uid_medico="u1",
                      conducta_clinica="Biopsia", fecha_cierre=AHORA)
    evento = EventoAuditoria(id="e1", tipo=TipoEvento.VALIDACION, referencia="c1", uid_actor="u1",
                             actor_nombre="Dra. A", fecha=AHORA, detalle={"concordante": False})
    for entidad in (validacion, informe, evento):
        assert ida_y_vuelta(entidad) == entidad
