"""Firebase Admin SDK: verificación de ID token, alta de cuentas y Cloud Messaging."""

from __future__ import annotations

from collections.abc import Sequence

import firebase_admin
from firebase_admin import auth, messaging

from ..dominio.errores import Conflicto, NoAutenticado, PermisoDenegado
from ..dominio.modelos import Rol


def iniciar_app(proyecto: str | None) -> firebase_admin.App:
    try:
        return firebase_admin.get_app()
    except ValueError:
        opciones = {"projectId": proyecto} if proyecto else None
        return firebase_admin.initialize_app(options=opciones)


class VerificadorFirebase:
    """Valida el ID token de la app. No consulta la revocación (sería una llamada más por
    solicitud): los permisos se leen del perfil en Firestore en cada solicitud, y al quitar el
    acceso clínico también se revocan las sesiones."""

    def __init__(self, app: firebase_admin.App):
        self._app = app

    def verificar(self, token: str) -> str:
        try:
            return auth.verify_id_token(token, app=self._app)["uid"]
        except (auth.InvalidIdTokenError, ValueError):
            raise NoAutenticado() from None


class CuentasFirebase:
    def __init__(self, app: firebase_admin.App):
        self._app = app

    def crear(self, correo: str, nombres: str) -> str:
        try:
            return auth.create_user(email=correo, display_name=nombres, app=self._app).uid
        except auth.EmailAlreadyExistsError:
            raise Conflicto("Ya existe una cuenta con ese correo.") from None

    def fijar_rol(self, uid: str, rol: Rol) -> None:
        auth.set_custom_user_claims(uid, {"rol": rol.value}, app=self._app)

    def revocar_sesiones(self, uid: str) -> None:
        auth.revoke_refresh_tokens(uid, app=self._app)


class PushFCM:
    def __init__(self, app: firebase_admin.App):
        self._app = app

    def enviar(self, tokens: Sequence[str], titulo: str, cuerpo: str,
               datos: dict[str, str]) -> list[str]:
        mensaje = messaging.MulticastMessage(
            tokens=list(tokens),
            notification=messaging.Notification(title=titulo, body=cuerpo),
            data=datos,
            android=messaging.AndroidConfig(priority="high"),
        )
        respuesta = messaging.send_each_for_multicast(mensaje, app=self._app)
        return [token for token, r in zip(tokens, respuesta.responses)
                if not r.success and isinstance(
                    r.exception, (messaging.UnregisteredError, messaging.SenderIdMismatchError))]


class VerificadorTareasOIDC:
    """Las tareas de Cloud Scheduler llegan con un token OIDC de su cuenta de servicio."""

    def __init__(self, audiencia: str, cuenta_servicio: str):
        self._audiencia = audiencia
        self._cuenta = cuenta_servicio

    def verificar(self, token: str) -> None:
        from google.auth.transport.requests import Request
        from google.oauth2 import id_token

        try:
            datos = id_token.verify_oauth2_token(token, Request(), audience=self._audiencia)
        except ValueError:
            raise NoAutenticado() from None
        if datos.get("email") != self._cuenta or not datos.get("email_verified"):
            raise PermisoDenegado()
