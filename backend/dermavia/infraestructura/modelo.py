"""Carga del artefacto versionado del modelo: `artefacto.json` + el `.tflite` que nombra.

En producción vive en Cloud Storage, en `<DERMAVIA_MODELO_URI>/<version>/`; la versión activa es
una variable de configuración del servicio (RNF-13). En local se lee de un directorio, por
ejemplo `outputs/exp04/20261004T172732Z_registro/`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from ..dominio.inferencia import Artefacto, ErrorArtefacto


def desde_directorio(directorio: Path) -> Callable[[], Artefacto]:
    def cargar() -> Artefacto:
        meta = (directorio / "artefacto.json").read_bytes()
        modelo = (directorio / json.loads(meta)["model_file"]).read_bytes()
        return Artefacto.desde_archivos(meta, modelo)

    return cargar


def desde_gcs(uri: str, version: str) -> Callable[[], Artefacto]:
    if not uri.startswith("gs://"):
        raise ErrorArtefacto(f"URI de Cloud Storage no válida: {uri}")
    bucket, _, prefijo = uri.removeprefix("gs://").partition("/")
    base = f"{prefijo.strip('/')}/{version}".lstrip("/")

    def cargar() -> Artefacto:
        from google.cloud import storage

        cubeta = storage.Client().bucket(bucket)
        meta = cubeta.blob(f"{base}/artefacto.json").download_as_bytes()
        modelo = cubeta.blob(f"{base}/{json.loads(meta)['model_file']}").download_as_bytes()
        return Artefacto.desde_archivos(meta, modelo)

    return cargar
