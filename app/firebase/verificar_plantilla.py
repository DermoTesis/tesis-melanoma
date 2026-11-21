"""Verifica la plantilla del correo para definir la contraseña (CONEXION_NUBE.md, C2).

Firebase usa la plantilla de "restablecer contraseña" para la activación de una cuenta
nueva y para la recuperación (I15, I16). Hoy Firebase no deja editar las plantillas de
este proyecto, ni por API (`EMAIL_TEMPLATE_UPDATE_NOT_ALLOWED`) ni en la consola; si el
soporte lo habilita, la plantilla se pega en la consola (Authentication → Plantillas →
Restablecimiento de contraseña). Este script, con las credenciales de gcloud, compara lo
publicado con plantilla_restablecer_contrasena.html:

    python firebase/verificar_plantilla.py     # desde app/
"""

import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROYECTO = "tesis-dermavia"
URL = f"https://identitytoolkit.googleapis.com/admin/v2/projects/{PROYECTO}/config"
PLANTILLA = Path(__file__).with_name("plantilla_restablecer_contrasena.html")

ESPERADO = {
    "defaultLocale": "es",
    "senderDisplayName": "Dermavía",
    "subject": "Define tu contraseña de Dermavía",
}


def token() -> str:
    gcloud = shutil.which("gcloud") or shutil.which("gcloud.cmd")
    if gcloud is None:
        sys.exit("No se encontró gcloud en el PATH.")
    return subprocess.run([gcloud, "auth", "print-access-token"], check=True,
                          capture_output=True, text=True).stdout.strip()


def config() -> dict:
    req = urllib.request.Request(URL, headers={
        "Authorization": f"Bearer {token()}",
        "x-goog-user-project": PROYECTO,
    })
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode("utf-8"))["notification"]
    except urllib.error.HTTPError as e:
        sys.exit(f"{e.code}: {e.read().decode('utf-8')}")


def normalizar(html: str) -> str:
    return " ".join(html.split())


def main() -> None:
    notificacion = config()
    plantilla = notificacion["sendEmail"]["resetPasswordTemplate"]
    actual = {
        "defaultLocale": notificacion.get("defaultLocale"),
        "senderDisplayName": plantilla.get("senderDisplayName"),
        "subject": plantilla.get("subject"),
    }
    ok = True
    for campo, valor in ESPERADO.items():
        bien = actual[campo] == valor
        ok &= bien
        print(f"[{'ok' if bien else 'NO'}] {campo}: {actual[campo]!r} (esperado {valor!r})")
    igual = normalizar(plantilla.get("body", "")) == normalizar(PLANTILLA.read_text(encoding="utf-8"))
    ok &= igual
    print(f"[{'ok' if igual else 'NO'}] cuerpo igual a {PLANTILLA.name}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
