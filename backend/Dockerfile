# Imagen del backend para Cloud Run. Se construye desde la raíz del repo, porque el módulo
# Inferencia usa `melanoma.serving` (src/melanoma):
#   docker build -f backend/Dockerfile -t dermavia-backend .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# Dependencias primero, para aprovechar la caché de capas.
COPY backend/pyproject.toml /srv/backend/pyproject.toml
RUN mkdir -p /srv/backend/dermavia && touch /srv/backend/dermavia/__init__.py \
    && pip install "/srv/backend[gcp]" && pip uninstall -y dermavia-backend \
    && rm -rf /srv/backend/dermavia /srv/backend/build /srv/backend/*.egg-info

# Paquete de los experimentos sin sus dependencias (pandas, scikit-learn, TensorFlow): el
# backend solo usa melanoma.serving, que necesita numpy, Pillow y LiteRT.
COPY pyproject.toml /srv/melanoma/pyproject.toml
COPY src/melanoma /srv/melanoma/src/melanoma
RUN pip install --no-deps /srv/melanoma

COPY backend/dermavia /srv/backend/dermavia
RUN pip install --no-deps /srv/backend && rm -rf /srv/backend /srv/melanoma

RUN useradd --uid 10001 --no-create-home dermavia
USER dermavia

EXPOSE 8080
# Una instancia de Cloud Run: 2 vCPU, 2 GB, concurrencia 4 (los endpoints corren en hilos).
CMD ["sh", "-c", "exec uvicorn dermavia.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8080} --no-access-log"]
