"""Publica en Cloud Storage el artefacto versionado del modelo (HU19, RNF-13).

Sube `artefacto.json` y el `.tflite` que nombra a `<destino>/<version>/`, después de comprobar
que el sha256 coincide. Una versión publicada no se sobrescribe nunca: si ya existe, falla.
Para activarla, se cambia `DERMAVIA_MODELO_VERSION` en el servicio de Cloud Run (sin recompilar).

    python scripts/publicar_modelo.py --destino gs://<bucket>/modelos \
        [--artefacto ../outputs/exp04/20261004T172732Z_registro]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dermavia.config import ARTEFACTO_LOCAL
from dermavia.dominio.inferencia import Artefacto


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--destino", required=True, help="gs://<bucket>/modelos")
    parser.add_argument("--artefacto", type=Path, default=ARTEFACTO_LOCAL)
    args = parser.parse_args()

    meta_bytes = (args.artefacto / "artefacto.json").read_bytes()
    meta = json.loads(meta_bytes)
    modelo = (args.artefacto / meta["model_file"]).read_bytes()
    artefacto = Artefacto.desde_archivos(meta_bytes, modelo)  # valida sha256 y campos

    if not args.destino.startswith("gs://"):
        parser.error("--destino debe empezar con gs://")
    bucket, _, prefijo = args.destino.removeprefix("gs://").partition("/")
    base = f"{prefijo.strip('/')}/{artefacto.version}".lstrip("/")

    from google.cloud import storage

    cubeta = storage.Client().bucket(bucket)
    # if_generation_match=0: solo crea; si la versión ya existe, Cloud Storage responde 412.
    cubeta.blob(f"{base}/{meta['model_file']}").upload_from_string(
        modelo, content_type="application/octet-stream", if_generation_match=0)
    cubeta.blob(f"{base}/artefacto.json").upload_from_string(
        meta_bytes, content_type="application/json", if_generation_match=0)
    print(f"Publicado gs://{bucket}/{base}/ (sha256 {artefacto.sha256[:12]}…)")
    print(f"Para activarlo: DERMAVIA_MODELO_VERSION={artefacto.version}")


if __name__ == "__main__":
    main()
