"""Envía la push de casos vencidos a los dispositivos de una cuenta (CONEXION_NUBE.md, N11).

Es el mismo mensaje que manda la tarea horaria del backend
(`backend/dermavia/dominio/notificaciones.py` y `infraestructura/firebase.py`), sin
esperar a que un caso pase las 48 h. Lee los tokens que la app registró con
`POST /users/me/devices` (Firestore, `usuarios/{uid}.tokens_dispositivo`) y envía con
FCM HTTP v1, con las credenciales de gcloud:

    python firebase/enviar_push_prueba.py lramirez@hospital.gob.pe --validar   # no envía
    python firebase/enviar_push_prueba.py lramirez@hospital.gob.pe             # envía

La cuenta tiene que haber iniciado sesión al menos una vez en el celular, con el
permiso de notificaciones concedido.
"""

import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

PROYECTO = "tesis-dermavia"
FIRESTORE = (f"https://firestore.googleapis.com/v1/projects/{PROYECTO}"
             "/databases/(default)/documents:runQuery")
FCM = f"https://fcm.googleapis.com/v1/projects/{PROYECTO}/messages:send"

# Igual que backend/dermavia/dominio/notificaciones.py.
TITULO = "Dermavía"
CUERPO = "Tienes casos pendientes de validación que superaron el tiempo límite."
DATOS = {"tipo": "casos_vencidos"}


def token() -> str:
    gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if gcloud is None:
        sys.exit("No se encontró gcloud en el PATH.")
    return subprocess.run([gcloud, "auth", "print-access-token"], check=True,
                          capture_output=True, text=True).stdout.strip()


def post(url: str, cuerpo: dict, acceso: str) -> tuple[int, object]:
    req = urllib.request.Request(
        url, data=json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {acceso}", "x-goog-user-project": PROYECTO,
                 "Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def tokens_de(correo: str, acceso: str) -> list[str]:
    estado, filas = post(FIRESTORE, {"structuredQuery": {
        "from": [{"collectionId": "usuarios"}],
        "where": {"fieldFilter": {"field": {"fieldPath": "correo"}, "op": "EQUAL",
                                  "value": {"stringValue": correo}}},
        "limit": 1,
    }}, acceso)
    if estado != 200:
        sys.exit(f"Firestore respondió {estado}: {filas}")
    documentos = [f["document"] for f in filas if "document" in f]
    if not documentos:
        sys.exit(f"No hay un usuario con el correo {correo}.")
    campo = documentos[0].get("fields", {}).get("tokens_dispositivo", {})
    return [v["stringValue"] for v in campo.get("arrayValue", {}).get("values", [])]


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    validar = "--validar" in sys.argv
    acceso = token()
    tokens = tokens_de(args[0].strip().lower(), acceso)
    if not tokens:
        sys.exit("La cuenta no tiene dispositivos registrados: inicia sesión en el celular "
                 "y concede el permiso de notificaciones.")
    print(f"{len(tokens)} dispositivo(s) registrado(s).")
    for i, t in enumerate(tokens, 1):
        estado, respuesta = post(FCM, {"validate_only": validar, "message": {
            "token": t,
            "notification": {"title": TITULO, "body": CUERPO},
            "data": DATOS,
            "android": {"priority": "HIGH"},
        }}, acceso)
        if estado == 200:
            print(f"  {i}. {'válido (no se envió)' if validar else 'enviado'}")
        else:
            error = respuesta.get("error", {}) if isinstance(respuesta, dict) else {}
            print(f"  {i}. error {estado}: {error.get('status')} {error.get('message', '')}")


if __name__ == "__main__":
    main()
