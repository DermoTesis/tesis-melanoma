"""Cloud Storage: bucket privado de imágenes clínicas con URL firmadas V4.

En Cloud Run la cuenta de servicio no tiene clave privada, así que la firma se pide a IAM
(signBlob) con el token de acceso de la propia cuenta. Para eso la cuenta necesita el rol
`roles/iam.serviceAccountTokenCreator` sobre sí misma (ver `backend/README.md`).
"""

from __future__ import annotations

from datetime import timedelta

import google.auth
from google.api_core.exceptions import NotFound
from google.auth.transport.requests import Request
from google.cloud import storage


class AlmacenGCS:
    def __init__(self, bucket: str, cliente: storage.Client | None = None):
        self._cliente = cliente or storage.Client()
        self._bucket = self._cliente.bucket(bucket)
        self._credenciales, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"])

    def _firma(self) -> dict[str, str]:
        # Con una clave de cuenta de servicio (desarrollo) la biblioteca firma sola.
        if hasattr(self._credenciales, "sign_bytes") and hasattr(self._credenciales, "signer"):
            return {}
        if not self._credenciales.valid:
            self._credenciales.refresh(Request())
        return {"service_account_email": self._credenciales.service_account_email,
                "access_token": self._credenciales.token}

    def url_subida(self, ruta: str, tipo_contenido: str, vigencia: timedelta) -> str:
        return self._bucket.blob(ruta).generate_signed_url(
            version="v4", expiration=vigencia, method="PUT", content_type=tipo_contenido,
            **self._firma())

    def url_lectura(self, ruta: str, vigencia: timedelta) -> str:
        return self._bucket.blob(ruta).generate_signed_url(
            version="v4", expiration=vigencia, method="GET", **self._firma())

    def leer(self, ruta: str) -> bytes | None:
        try:
            return self._bucket.blob(ruta).download_as_bytes()
        except NotFound:
            return None
