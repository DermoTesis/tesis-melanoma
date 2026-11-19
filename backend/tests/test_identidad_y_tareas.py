"""Identidad (alta, activación, alcance, permisos), alertas de vencidos y configuración."""

from __future__ import annotations

import pytest
from conftest import ADMIN, ESP, TAREAS, caso_con_prediccion, h

from dermavia.config import Configuracion, ErrorConfiguracion
from dermavia.dominio.modelos import TipoEvento
from dermavia.dominio.notificaciones import CUERPO


def test_alta_activacion_y_aceptacion_del_alcance(cliente, cuentas, registro):
    datos = {"nombres": "Dra. Ana Torres", "correo": "ATorres@Hospital.gob.pe", "dni": "45678912",
             "numero_colegiatura": "45123", "colegiatura_verificada": False}
    r = cliente.post("/admin/specialists", headers=ADMIN, json=datos)
    assert r.status_code == 422  # sin verificar la colegiatura no hay alta

    r = cliente.post("/admin/specialists", headers=ADMIN,
                     json={**datos, "colegiatura_verificada": True})
    assert r.status_code == 201, r.text
    nuevo = r.json()
    assert nuevo["correo"] == "atorres@hospital.gob.pe"
    assert nuevo["estado"] == "PENDIENTE_ACTIVACION"
    assert nuevo["establecimiento"] == "Hospital de demostración"
    assert cuentas.roles[nuevo["uid"]] == "especialista"

    assert cliente.post("/admin/specialists", headers=ADMIN,
                        json={**datos, "colegiatura_verificada": True}).status_code == 409

    yo = cliente.get("/users/me", headers=h(nuevo["uid"])).json()
    assert yo["estado"] == "ACTIVO" and yo["requiere_aceptar_alcance"]
    assert cliente.get("/cases", headers=h(nuevo["uid"])).status_code == 403
    cliente.post("/users/me/terms", headers=h(nuevo["uid"]))
    assert cliente.get("/cases", headers=h(nuevo["uid"])).status_code == 200
    tipos = [e.tipo for e in registro.eventos]
    assert TipoEvento.ACTIVACION_CUENTA in tipos and TipoEvento.ACEPTACION_ALCANCE in tipos


def test_revocar_acceso_clinico(cliente, cuentas):
    r = cliente.patch("/admin/users/especialista-dev/role", headers=ADMIN,
                      json={"acceso_clinico": False})
    assert r.status_code == 200
    assert cliente.get("/cases", headers=ESP).status_code == 403
    assert "especialista-dev" in cuentas.revocadas


def test_solo_el_admin_gestiona_usuarios_y_ve_la_bitacora(cliente):
    assert cliente.get("/admin/users", headers=ESP).status_code == 403
    assert cliente.get("/admin/audit", headers=ESP).status_code == 403
    assert len(cliente.get("/admin/users", headers=ADMIN).json()) == 3
    assert cliente.patch("/admin/users/admin-dev/role", headers=ADMIN,
                         json={"rol": "especialista"}).status_code == 422


def test_sin_token_o_cuenta_desconocida(cliente):
    assert cliente.get("/users/me").status_code == 401
    assert cliente.get("/users/me", headers={"Authorization": "Bearer otro"}).status_code == 401
    r = cliente.get("/users/me", headers=h("uid-sin-perfil"))
    assert r.status_code == 403


def test_alerta_de_vencidos_una_vez_y_sin_datos_clinicos(cliente, almacen, motor, push, reloj,
                                                         contenedor):
    cliente.post("/users/me/devices", headers=ESP, json={"token": "token-viejo"})
    cliente.post("/users/me/devices", headers=ESP, json={"token": "token-celular"})
    caso_con_prediccion(cliente, almacen, motor)

    reloj.avanzar(hours=47)
    assert cliente.post("/tasks/overdue-alerts", headers=TAREAS).json()["resumen"]["casos"] == 0
    reloj.avanzar(hours=2)
    assert cliente.post("/tasks/overdue-alerts", headers=TAREAS).json()["resumen"]["casos"] == 1
    assert cliente.post("/tasks/overdue-alerts", headers=TAREAS).json()["resumen"]["casos"] == 0

    (enviado,) = push.enviados
    assert enviado["tokens"] == ["token-viejo", "token-celular"]
    assert enviado["cuerpo"] == CUERPO
    assert "Rosa" not in str(enviado) and "Espalda" not in str(enviado)
    # El token que FCM rechazó se borra del perfil.
    assert contenedor.identidad.obtener("especialista-dev").tokens_dispositivo == (
        "token-celular",)
    assert cliente.get("/cases", headers=ESP).json()[0]["alerta_vencido"] is True


def test_health(cliente):
    r = cliente.get("/health")
    assert r.json() == {"estado": "ok", "version_modelo": "20261004T172732Z_registro"}


def test_configuracion_local_prohibida_en_cloud_run():
    with pytest.raises(ErrorConfiguracion):
        Configuracion.desde_entorno({"DERMAVIA_ENTORNO": "local", "K_SERVICE": "dermavia"})


def test_configuracion_nube_exige_variables():
    with pytest.raises(ErrorConfiguracion, match="DERMAVIA_BUCKET_IMAGENES"):
        Configuracion.desde_entorno({"GOOGLE_CLOUD_PROJECT": "p"})
