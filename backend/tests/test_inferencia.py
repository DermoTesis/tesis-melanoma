"""Módulo Inferencia: regla de decisión del registro de EXP-04, errores, reintentos y el modelo real."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from conftest import ESP, RAIZ, TAREAS, artefacto_del_registro, caso_con_prediccion, jpeg

from dermavia.dominio.inferencia import Artefacto, ErrorArtefacto, ModuloInferencia, MotorLiteRT
from dermavia.dominio.modelos import ClaseLesion

ARTEFACTO = RAIZ / "outputs/exp04/20261004T172732Z_registro"
IMAGENES = RAIZ / "data/ham10000/images"


@pytest.mark.parametrize("salida, clase, probabilidad", [
    (0.0139, ClaseLesion.MELANOMA, 0.0699),     # justo sobre el umbral 0.01378
    (0.0137, ClaseLesion.NO_MELANOMA, 0.0699),  # justo bajo: misma probabilidad mostrada
    (0.002, ClaseLesion.NO_MELANOMA, 0.0279),
    (0.9, ClaseLesion.MELANOMA, 0.7468),
])
def test_clase_con_salida_sin_calibrar(salida, clase, probabilidad):
    artefacto = artefacto_del_registro()
    assert artefacto.clase(salida) == clase
    assert artefacto.calibrar(salida) == pytest.approx(probabilidad, abs=1e-4)


def test_el_escalon_de_la_calibracion_no_decide_la_clase(cliente, almacen, motor):
    """Dos casos con el mismo 7% mostrado: uno con alerta y otro sin ella (pendiente A5)."""
    con_alerta = caso_con_prediccion(cliente, almacen, motor, salida=0.0139, hc="HC-1")
    sin_alerta = caso_con_prediccion(cliente, almacen, motor, salida=0.0137, hc="HC-2")
    p1, p2 = con_alerta["prediccion"], sin_alerta["prediccion"]
    assert p1["probabilidad_malignidad"] == p2["probabilidad_malignidad"]
    assert (p1["clase_predicha"], p2["clase_predicha"]) == ("melanoma", "no_melanoma")
    assert (p1["banda"], p2["banda"]) == ("baja", "sin_alerta")
    assert sin_alerta["sugerencia_examenes"] is None


def test_fallo_del_analisis_y_reproceso(cliente, almacen, motor, reloj):
    motor.error = RuntimeError("se cayó el intérprete")
    caso = caso_con_prediccion(cliente, almacen, motor)
    assert caso["estado"] == "ERROR_ANALISIS"
    assert caso["ultimo_error"]

    motor.error = None
    r = cliente.post("/tasks/reprocess", headers=TAREAS)
    assert r.json()["resumen"]["con_prediccion"] == 1
    caso = cliente.get(f"/cases/{caso['id']}", headers=ESP).json()
    assert caso["estado"] == "PENDIENTE_VALIDACION"
    assert caso["intentos_analisis"] == 2


def test_el_reproceso_se_detiene_tras_varios_intentos(cliente, almacen, motor):
    motor.error = RuntimeError("persistente")
    caso_con_prediccion(cliente, almacen, motor)
    for _ in range(10):
        cliente.post("/tasks/reprocess", headers=TAREAS)
    assert motor.llamadas == 5


def test_analisis_colgado_se_recupera(cliente, almacen, motor, contenedor, reloj):
    """Si la instancia se apagó en pleno análisis, el caso queda EN_ANALISIS y la tarea lo retoma."""
    from dataclasses import replace

    from dermavia.dominio.modelos import EstadoCaso

    caso = caso_con_prediccion(cliente, almacen, motor)
    repo = contenedor.casos._casos
    repo.actualizar(caso["id"], lambda c: replace(
        c, estado=EstadoCaso.EN_ANALISIS, prediccion=None, fecha_inicio_analisis=reloj.ahora()))
    assert cliente.post("/tasks/reprocess", headers=TAREAS).json()["resumen"]["candidatos"] == 0
    reloj.avanzar(minutes=11)
    assert cliente.post("/tasks/reprocess", headers=TAREAS).json()["resumen"][
        "con_prediccion"] == 1


def test_tareas_exigen_el_token_de_cloud_scheduler(cliente):
    assert cliente.post("/tasks/reprocess").status_code == 401
    assert cliente.post("/tasks/reprocess", headers=ESP).status_code == 401


def test_artefacto_rechaza_un_modelo_alterado():
    meta = json.dumps({
        "version": "v", "sha256": hashlib.sha256(b"original").hexdigest(), "image_size": 224,
        "inputs": ["view_a", "view_b"], "threshold": 0.5, "calibrated_threshold": 0.5,
        "calibration": {"method": "isotonic", "x": [0, 1], "y": [0, 1]}, "model_file": "m",
    }).encode()
    assert Artefacto.desde_archivos(meta, b"original").version == "v"
    with pytest.raises(ErrorArtefacto, match="sha256"):
        Artefacto.desde_archivos(meta, b"alterado")


requiere_modelo = pytest.mark.skipif(
    not (ARTEFACTO / "artefacto.json").exists() or not IMAGENES.exists(),
    reason="Falta el artefacto de EXP-04 en outputs/ o las imágenes de HAM10000 en data/")


@requiere_modelo
def test_modelo_real_igual_que_melanoma_serving(reloj):
    """El backend da exactamente lo mismo que el código con el que EXP-04 fijó el umbral."""
    from melanoma.serving import TFLiteClassifier, preprocess

    from dermavia.infraestructura.modelo import desde_directorio

    artefacto = desde_directorio(ARTEFACTO)()
    assert artefacto.version == "20261004T172732Z_registro"
    inferencia = ModuloInferencia(lambda: artefacto, reloj, MotorLiteRT)

    referencia = TFLiteClassifier(artefacto.modelo, num_threads=2)
    fotos = sorted(IMAGENES.glob("*.jpg"))[:6]
    for a, b in zip(fotos[0::2], fotos[1::2]):
        datos_a, datos_b = a.read_bytes(), b.read_bytes()
        prediccion = inferencia.predecir(datos_a, datos_b)
        esperado = referencia.predict_case(preprocess(datos_a), preprocess(datos_b))[0]
        assert prediccion.salida_modelo == pytest.approx(esperado, abs=1e-7)
        assert prediccion.probabilidad_malignidad == pytest.approx(
            float(np.interp(esperado, artefacto.calibracion_x, artefacto.calibracion_y)))
        assert prediccion.clase_predicha == artefacto.clase(esperado)
        assert prediccion.sha256_modelo == artefacto.sha256


@requiere_modelo
def test_modelo_real_con_imagen_invalida(reloj):
    from dermavia.dominio.errores import ImagenInvalida
    from dermavia.infraestructura.modelo import desde_directorio

    inferencia = ModuloInferencia(desde_directorio(ARTEFACTO), reloj, MotorLiteRT)
    with pytest.raises(ImagenInvalida):
        inferencia.predecir(b"no es una foto", jpeg())
    assert 0.0 <= inferencia.predecir(jpeg(), jpeg((90, 60, 40))).probabilidad_malignidad <= 1.0


def test_ruta_del_artefacto_es_la_del_registro():
    assert Path(ARTEFACTO).name == json.loads(
        (RAIZ / "resultados/exp04/20261004T172732Z_registro/registro.json").read_text()
    )["artifact"]["version"]
