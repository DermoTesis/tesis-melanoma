#!/usr/bin/env bash
# Corre un script de Python del repo dentro de la imagen de NVIDIA (plan A, ver README):
#
#   bash scripts/gpu.sh experiments/exp02_mobilenetv3.py [--set clave=valor ...]
#
# La primera vez crea .venv-gpu (fuera de git) heredando el TensorFlow de la imagen e instala el
# paquete del repo sin tocar el numpy de la imagen. Se hace con el python de la imagen y sin pip
# propio (--without-pip), porque la imagen puede no traer ensurepip.
set -euo pipefail
cd "$(dirname "$0")/.."

VENV=.venv-gpu
if [ ! -x "$VENV/bin/python" ]; then
  echo "Creando $VENV (solo la primera vez)..."
  python -m venv --without-pip --system-site-packages "$VENV"
  numpy_version=$(python -c 'import numpy; print(numpy.__version__)')
  "$VENV/bin/python" -m pip install --quiet --no-cache-dir -e . "numpy==$numpy_version"
fi
# Oculta los avisos de TensorFlow de nivel INFO/WARNING (en esta GPU llenan la pantalla).
export TF_CPP_MIN_LOG_LEVEL="${TF_CPP_MIN_LOG_LEVEL:-2}"
exec "$VENV/bin/python" "$@"
