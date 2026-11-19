"""Flujo obligatorio completo por la API y las barreras que no se pueden saltar (RF-07.1)."""

from __future__ import annotations

from conftest import (
    ADMIN, ESP, caso_con_prediccion, cargar_fotos, crear_caso, crear_paciente, h,
)

from dermavia.dominio.modelos import TipoEvento


def test_flujo_completo_registro_prediccion_validacion_cierre(cliente, almacen, motor, registro):
    paciente = crear_paciente(cliente)
    assert paciente["consentimiento_vigente"]

    caso = crear_caso(cliente, paciente["id"])
    assert caso["estado"] == "REGISTRADO"
    assert caso["prediccion"] is None

    cargar_fotos(cliente, almacen, caso["id"])
    motor.salida_siguiente = 0.5
    r = cliente.post(f"/cases/{caso['id']}/submit", headers=ESP)
    assert r.status_code == 200
    caso = r.json()
    assert caso["estado"] == "PENDIENTE_VALIDACION"
    assert caso["vistas_cargadas"] == ["a", "b"]
    prediccion = caso["prediccion"]
    assert prediccion["clase_predicha"] == "melanoma"
    assert prediccion["version_modelo"] == "20261004T172732Z_registro"
    # La API no expone con qué recalcular la clase.
    assert "salida_modelo" not in prediccion and "umbral_operativo" not in prediccion

    assert cliente.get("/cases/pending", headers=ESP).json()[0]["id"] == caso["id"]

    r = cliente.post("/validations", headers=ESP, json={
        "id_caso": caso["id"], "decision": "confirmar",
        "sustento_clinico": "Red pigmentada atípica y velo azul-blanquecino."})
    assert r.status_code == 201, r.text
    validacion = r.json()
    assert validacion["clase_final"] == "melanoma"
    assert validacion["numero_colegiatura"] == "12345"
    assert cliente.get(f"/cases/{caso['id']}/status", headers=ESP).json()["estado"] == "VALIDADO"

    cliente.post(f"/cases/{caso['id']}/notes", headers=ESP,
                 json={"texto": "Nota interna: paciente ansiosa."})
    r = cliente.post(f"/cases/{caso['id']}/close", headers=ESP,
                     json={"conducta_clinica": "Biopsia escisional en 2 semanas."})
    assert r.status_code == 200, r.text
    assert cliente.get(f"/cases/{caso['id']}/status", headers=ESP).json()["estado"] == "CERRADO"

    informe = cliente.get(f"/reports/{caso['id']}", headers=ESP).json()
    assert informe["conclusion"] == "Lesión compatible con melanoma."
    assert informe["conducta_clinica"] == "Biopsia escisional en 2 semanas."
    assert "apoyo diagnóstico" in informe["alcance"]
    texto = str(informe)
    assert "Nota interna" not in texto and "probabilidad" not in texto

    tipos = [e.tipo for e in registro.eventos]
    for esperado in (TipoEvento.REGISTRO_PACIENTE, TipoEvento.CONSENTIMIENTO,
                     TipoEvento.REGISTRO_CASO, TipoEvento.PREDICCION, TipoEvento.VALIDACION,
                     TipoEvento.CIERRE_CASO):
        assert esperado in tipos
    evento_validacion = next(e for e in registro.eventos if e.tipo == TipoEvento.VALIDACION)
    assert evento_validacion.detalle["concordante"] is True


def test_sin_consentimiento_no_hay_caso(cliente):
    paciente = crear_paciente(cliente, consentimiento=False)
    r = cliente.post("/cases", headers=ESP, json={
        "id_paciente": paciente["id"],
        "datos_clinicos": {"ubicacion_lesion": "Brazo", "tiempo_aparicion": "no_sabe"}})
    assert r.status_code == 409
    assert r.json()["error"]["codigo"] == "consent-required"


def test_revocar_consentimiento_bloquea_el_envio(cliente, almacen):
    paciente = crear_paciente(cliente)
    caso = crear_caso(cliente, paciente["id"])
    cargar_fotos(cliente, almacen, caso["id"])
    assert cliente.delete(f"/patients/{paciente['id']}/consent", headers=ESP).status_code == 200
    r = cliente.post(f"/cases/{caso['id']}/submit", headers=ESP)
    assert r.json()["error"]["codigo"] == "consent-required"


def test_enviar_sin_las_dos_fotos(cliente, almacen):
    paciente = crear_paciente(cliente)
    caso = crear_caso(cliente, paciente["id"])
    r = cliente.post(f"/cases/{caso['id']}/submit", headers=ESP)
    assert r.status_code == 422
    assert cliente.get(f"/cases/{caso['id']}/status", headers=ESP).json()["estado"] == "REGISTRADO"


def test_reenvio_de_la_cola_offline_no_duplica(cliente, almacen, motor):
    paciente = crear_paciente(cliente)
    primero = crear_caso(cliente, paciente["id"], id_solicitud="cola-123")
    segundo = crear_caso(cliente, paciente["id"], id_solicitud="cola-123")
    assert primero["id"] == segundo["id"]
    cargar_fotos(cliente, almacen, primero["id"])
    cliente.post(f"/cases/{primero['id']}/submit", headers=ESP)
    cliente.post(f"/cases/{primero['id']}/submit", headers=ESP)  # reenvío
    assert motor.llamadas == 1


def test_no_se_cierra_sin_validacion(cliente, almacen, motor):
    caso = caso_con_prediccion(cliente, almacen, motor)
    r = cliente.post(f"/cases/{caso['id']}/close", headers=ESP,
                     json={"conducta_clinica": "Control en 3 meses."})
    assert r.status_code == 409
    assert r.json()["error"]["codigo"] == "validation-required"
    assert cliente.get(f"/reports/{caso['id']}", headers=ESP).json()["error"]["codigo"] == \
        "validation-required"


def test_validacion_exige_sustento_y_clase_distinta_al_corregir(cliente, almacen, motor):
    caso = caso_con_prediccion(cliente, almacen, motor, salida=0.5)
    base = {"id_caso": caso["id"], "decision": "confirmar"}
    r = cliente.post("/validations", headers=ESP, json={**base, "sustento_clinico": "   "})
    assert r.status_code == 422
    r = cliente.post("/validations", headers=ESP, json={
        **base, "decision": "corregir", "clase_final": "melanoma", "sustento_clinico": "x"})
    assert r.status_code == 422
    r = cliente.post("/validations", headers=ESP, json={
        **base, "decision": "corregir", "clase_final": "no_melanoma",
        "sustento_clinico": "Patrón globular simétrico de nevo."})
    assert r.status_code == 201
    assert r.json()["clase_final"] == "no_melanoma"


def test_validacion_inmutable_solo_complementaria(cliente, almacen, motor):
    caso = caso_con_prediccion(cliente, almacen, motor)
    datos = {"id_caso": caso["id"], "decision": "descartar", "sustento_clinico": "Foto movida."}
    primera = cliente.post("/validations", headers=ESP, json=datos).json()
    assert primera["clase_final"] is None

    r = cliente.post("/validations", headers=ESP, json=datos)
    assert r.status_code == 409

    r = cliente.post("/validations", headers=ESP, json={
        **datos, "decision": "confirmar", "sustento_clinico": "Revisada con nueva foto.",
        "complementa_de": primera["id"]})
    assert r.status_code == 201
    validaciones = cliente.get(f"/cases/{caso['id']}/validations", headers=ESP).json()
    assert [v["decision"] for v in validaciones] == ["descartar", "confirmar"]
    assert validaciones[0]["sustento_clinico"] == "Foto movida."  # la original no cambió


def test_sugerencia_solo_editable_antes_de_validar(cliente, almacen, motor):
    caso = caso_con_prediccion(cliente, almacen, motor, salida=0.10)  # calibrada a 0.175
    assert caso["prediccion"]["banda"] == "baja"
    assert "control dermatoscópico" in caso["sugerencia_examenes"]
    r = cliente.put(f"/cases/{caso['id']}/suggestion", headers=ESP, json={"texto": "Biopsia."})
    assert r.json()["sugerencia_examenes"] == "Biopsia."
    cliente.post("/validations", headers=ESP, json={
        "id_caso": caso["id"], "decision": "confirmar", "sustento_clinico": "Asimetría."})
    r = cliente.put(f"/cases/{caso['id']}/suggestion", headers=ESP, json={"texto": "Otra."})
    assert r.status_code == 409


def test_cierre_unico(cliente, almacen, motor):
    caso = caso_con_prediccion(cliente, almacen, motor)
    cliente.post("/validations", headers=ESP, json={
        "id_caso": caso["id"], "decision": "confirmar", "sustento_clinico": "Asimetría."})
    datos = {"conducta_clinica": "Biopsia."}
    assert cliente.post(f"/cases/{caso['id']}/close", headers=ESP, json=datos).status_code == 200
    assert cliente.post(f"/cases/{caso['id']}/close", headers=ESP, json=datos).status_code == 409


def test_otro_medico_no_ve_el_caso_pero_si_el_historial(cliente, almacen, motor, contenedor):
    caso = caso_con_prediccion(cliente, almacen, motor)
    cliente.post("/validations", headers=ESP, json={
        "id_caso": caso["id"], "decision": "confirmar", "sustento_clinico": "Asimetría."})
    cliente.post(f"/cases/{caso['id']}/close", headers=ESP, json={"conducta_clinica": "Biopsia."})

    otro = h("especialista-nuevo")
    cliente.post("/users/me/terms", headers=otro)
    assert cliente.get(f"/cases/{caso['id']}", headers=otro).status_code == 404
    historial = cliente.get(f"/patients/{caso['id_paciente']}/reports", headers=otro).json()
    assert [d["id_caso"] for d in historial] == [caso["id"]]


def test_hc_unica_y_busqueda(cliente):
    paciente = crear_paciente(cliente, hc="hc 0099")
    assert paciente["numero_historia_clinica"] == "HC0099"
    r = cliente.post("/patients", headers=ESP, json={
        "numero_historia_clinica": "HC0099", "nombres": "Otro", "fecha_nacimiento": "1990-01-01",
        "sexo": "masculino", "fototipo": "III"})
    assert r.status_code == 409
    assert cliente.get("/patients", headers=ESP, params={"hc": "hc0099"}).json()[0]["id"] == \
        paciente["id"]
    assert cliente.get("/patients", headers=ESP, params={"hc": "no-existe"}).json() == []


def test_admin_no_accede_a_funciones_clinicas(cliente):
    r = cliente.get("/patients", headers=ADMIN)
    assert r.status_code == 403
    assert r.json()["error"]["codigo"] == "permission-denied"


def test_formato_de_error_en_datos_mal_formados(cliente):
    r = cliente.post("/patients", headers=ESP, json={"nombres": "Sin HC"})
    assert r.status_code == 422
    assert r.json()["error"]["codigo"] == "invalid-argument"
    assert "numero_historia_clinica" in r.json()["error"]["campos"]
