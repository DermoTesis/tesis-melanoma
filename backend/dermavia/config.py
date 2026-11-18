"""Configuración del servicio por variables de entorno (las define el despliegue en Cloud Run).

| Variable | Uso |
|---|---|
| `DERMAVIA_ENTORNO` | `nube` (por defecto) o `local` (memoria, sin Google Cloud) |
| `GOOGLE_CLOUD_PROJECT` | proyecto de Google Cloud y de Firebase |
| `DERMAVIA_BUCKET_IMAGENES` | bucket privado de las fotos de los casos |
| `DERMAVIA_FIRESTORE_VALIDACIONES` | base de Firestore de solo inserción (`validaciones`) |
| `DERMAVIA_MODELO_URI` | `gs://<bucket>/modelos` en la nube, o un directorio en local |
| `DERMAVIA_MODELO_VERSION` | versión activa del artefacto (RNF-13), p. ej. `20261004T172732Z_registro` |
| `DERMAVIA_HILOS_INFERENCIA` | hilos de LiteRT (2, como las 2 vCPU de Cloud Run) |
| `DERMAVIA_HORAS_VENCIMIENTO` | tiempo límite de validación antes de alertar (48 h) |
| `DERMAVIA_TAREAS_AUDIENCIA` | audiencia del token OIDC de Cloud Scheduler (la URL del servicio) |
| `DERMAVIA_TAREAS_CUENTA` | cuenta de servicio con la que llama Cloud Scheduler |
| `DERMAVIA_URL_BASE` | solo local: URL del servidor, para las URL firmadas simuladas |
| `DERMAVIA_CARPETA_LOCAL` | solo local: carpeta donde se guardan las fotos |
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ARTEFACTO_LOCAL = Path(__file__).resolve().parents[2] / "outputs/exp04/20261004T172732Z_registro"


class ErrorConfiguracion(RuntimeError):
    pass


@dataclass(frozen=True)
class Configuracion:
    entorno: str = "nube"
    proyecto: str | None = None
    bucket_imagenes: str | None = None
    base_validaciones: str = "validaciones"
    modelo_uri: str | None = None
    modelo_version: str | None = None
    hilos_inferencia: int = 2
    horas_vencimiento: float = 48.0
    tareas_audiencia: str | None = None
    tareas_cuenta: str | None = None
    url_base: str = "http://localhost:8080"
    carpeta_local: Path = Path(".almacen-local")

    @property
    def es_local(self) -> bool:
        return self.entorno == "local"

    @classmethod
    def desde_entorno(cls, env: Mapping[str, str] = os.environ) -> Configuracion:
        config = cls(
            entorno=env.get("DERMAVIA_ENTORNO", "nube"),
            proyecto=env.get("GOOGLE_CLOUD_PROJECT"),
            bucket_imagenes=env.get("DERMAVIA_BUCKET_IMAGENES"),
            base_validaciones=env.get("DERMAVIA_FIRESTORE_VALIDACIONES", "validaciones"),
            modelo_uri=env.get("DERMAVIA_MODELO_URI"),
            modelo_version=env.get("DERMAVIA_MODELO_VERSION"),
            hilos_inferencia=int(env.get("DERMAVIA_HILOS_INFERENCIA", "2")),
            horas_vencimiento=float(env.get("DERMAVIA_HORAS_VENCIMIENTO", "48")),
            tareas_audiencia=env.get("DERMAVIA_TAREAS_AUDIENCIA"),
            tareas_cuenta=env.get("DERMAVIA_TAREAS_CUENTA"),
            url_base=env.get("DERMAVIA_URL_BASE", "http://localhost:8080"),
            carpeta_local=Path(env.get("DERMAVIA_CARPETA_LOCAL", ".almacen-local")),
        )
        if config.entorno not in ("nube", "local"):
            raise ErrorConfiguracion(f"DERMAVIA_ENTORNO no válido: {config.entorno}")
        # El modo local acepta tokens de desarrollo: nunca debe correr en Cloud Run.
        if config.es_local and "K_SERVICE" in env:
            raise ErrorConfiguracion("DERMAVIA_ENTORNO=local no se permite en Cloud Run.")
        if not config.es_local:
            faltan = [nombre for nombre, valor in [
                ("GOOGLE_CLOUD_PROJECT", config.proyecto),
                ("DERMAVIA_BUCKET_IMAGENES", config.bucket_imagenes),
                ("DERMAVIA_MODELO_URI", config.modelo_uri),
                ("DERMAVIA_MODELO_VERSION", config.modelo_version),
                ("DERMAVIA_TAREAS_AUDIENCIA", config.tareas_audiencia),
                ("DERMAVIA_TAREAS_CUENTA", config.tareas_cuenta),
            ] if not valor]
            if faltan:
                raise ErrorConfiguracion(f"Faltan variables de entorno: {', '.join(faltan)}")
        return config
