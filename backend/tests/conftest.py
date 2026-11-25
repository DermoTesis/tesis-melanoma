"""Fixtures: el backend completo con adaptadores en memoria, un reloj fijo y un motor falso.

El motor falso devuelve la salida sin calibrar que se le indique, y el artefacto usa la
calibración y el umbral reales del registro de EXP-04 (`resultados/`, en git), así que las
reglas de decisión se prueban con los parámetros de producción sin necesitar el `.tflite`.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from dermavia.contenedor import Contenedor, ensamblar
from dermavia.dominio.inferencia import Artefacto
from dermavia.infraestructura import memoria
from dermavia.local import sembrar
from dermavia.main import create_app

RAIZ = Path(__file__).resolve().parents[2]
REGISTRO = RAIZ / "resultados/exp04/20261004T172732Z_registro/registro.json"


class RelojFijo:
    def __init__(self):
        self.actual = datetime(2026, 11, 18, 15, 0, tzinfo=UTC)

    def ahora(self) -> datetime:
        return self.actual

    def avanzar(self, **kwargs) -> None:
        self.actual += timedelta(**kwargs)


class MotorFalso:
    def __init__(self):
        self.salida_siguiente = 0.5
        self.error: Exception | None = None
        self.llamadas = 0

    def salida(self, foto_a: bytes, foto_b: bytes) -> float:
        self.llamadas += 1
        if self.error is not None:
            raise self.error
        return self.salida_siguiente


def artefacto_del_registro() -> Artefacto:
    meta = json.loads(REGISTRO.read_text())["artifact"]
    return Artefacto(
        version=meta["version"], sha256=meta["sha256"], image_size=meta["image_size"],
        umbral=meta["threshold"], calibracion_x=tuple(meta["calibration"]["x"]),
        calibracion_y=tuple(meta["calibration"]["y"]),
        linea_alerta=meta["calibrated_threshold"], modelo=b"",
    )


def jpeg(color: tuple[int, int, int] = (180, 120, 90), tamano: tuple[int, int] = (64, 48)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", tamano, color).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture
def reloj() -> RelojFijo:
    return RelojFijo()


@pytest.fixture
def motor() -> MotorFalso:
    return MotorFalso()


@pytest.fixture
def almacen() -> memoria.AlmacenMemoria:
    return memoria.AlmacenMemoria()


@pytest.fixture
def push() -> memoria.PushMemoria:
    return memoria.PushMemoria(invalidos=["token-viejo"])


@pytest.fixture
def cuentas() -> memoria.CuentasMemoria:
    return memoria.CuentasMemoria()


@pytest.fixture
def registro() -> memoria.RegistroAuditoriaMemoria:
    return memoria.RegistroAuditoriaMemoria()


@pytest.fixture
def contenedor(reloj, motor, almacen, push, cuentas, registro) -> Contenedor:
    c = ensamblar(
        usuarios=memoria.RepoUsuariosMemoria(), pacientes=memoria.RepoPacientesMemoria(),
        casos=memoria.RepoCasosMemoria(), validaciones=memoria.RepoValidacionesMemoria(),
        informes=memoria.RepoInformesMemoria(), registro=registro, almacen=almacen,
        cuentas=cuentas, push=push, cargar_artefacto=artefacto_del_registro,
        verificador=memoria.VerificadorDesarrollo(),
        verificador_tareas=memoria.VerificadorTareasDesarrollo(), reloj=reloj,
        crear_motor=lambda artefacto: motor,
    )
    sembrar(c)
    return c


@pytest.fixture
def cliente(contenedor) -> TestClient:
    with TestClient(create_app(contenedor)) as cliente:
        yield cliente


def h(uid: str) -> dict[str, str]:
    return {"Authorization": f"Bearer dev:{uid}"}


ESP = h("especialista-dev")
ADMIN = h("admin-dev")
TAREAS = {"Authorization": "Bearer dev-tareas"}


def crear_paciente(cliente: TestClient, hc: str = "HC-0001", consentimiento: bool = True) -> dict:
    r = cliente.post("/patients", headers=ESP, json={
        "numero_historia_clinica": hc, "nombres": "Rosa Quispe Mamani",
        "fecha_nacimiento": "1968-04-02", "sexo": "femenino", "fototipo": "IV"})
    assert r.status_code == 201, r.text
    paciente = r.json()
    if consentimiento:
        r = cliente.post(f"/patients/{paciente['id']}/consent", headers=ESP)
        assert r.status_code == 200, r.text
        paciente = r.json()
    return paciente


def crear_caso(cliente: TestClient, id_paciente: str, **extra) -> dict:
    r = cliente.post("/cases", headers=ESP, json={
        "id_paciente": id_paciente,
        "datos_clinicos": {"ubicacion_lesion": "Espalda", "tiempo_aparicion": "menos_3_meses",
                           "sintomas": ["cambio_color", "picor"],
                           "impresion_clinica": "dudosa"},
        **extra})
    assert r.status_code == 201, r.text
    return r.json()


def cargar_fotos(cliente: TestClient, almacen: memoria.AlmacenMemoria, id_caso: str) -> None:
    for vista in ("a", "b"):
        r = cliente.post(f"/cases/{id_caso}/upload-url", headers=ESP,
                         json={"vista": vista, "tipo_contenido": "image/jpeg"})
        assert r.status_code == 200, r.text
        almacen.poner(r.json()["ruta"], jpeg())


def caso_con_prediccion(cliente, almacen, motor, salida: float = 0.5, hc: str = "HC-0001"):
    paciente = crear_paciente(cliente, hc)
    caso = crear_caso(cliente, paciente["id"])
    cargar_fotos(cliente, almacen, caso["id"])
    motor.salida_siguiente = salida
    r = cliente.post(f"/cases/{caso['id']}/submit", headers=ESP)
    assert r.status_code == 200, r.text
    return r.json()
