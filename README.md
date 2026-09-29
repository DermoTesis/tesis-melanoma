# Detección temprana de melanoma: experimentos del modelo

Tesis de pregrado UPC. Autores: Ilan Núñez del Arco y Jorge Orrego. Asesor: Carlos Alarcón.

Este repositorio contiene el código de los experimentos del clasificador. La app Flutter (solo
Android) la usa el médico especialista. La clasificación no corre en el celular, sino en el
backend (Cloud Run, CPU, 2 vCPU), con un modelo `.tflite` versionado en Cloud Storage. La tarea es
binaria (melanoma vs. el resto) y devuelve una probabilidad. La predicción es siempre preliminar
y la valida el médico.

## Estructura

```
configs/            base.yaml + un YAML por experimento (heredan con `extends`)
src/melanoma/       paquete con config, registro de corridas, datos, modelos, métricas, etc.
experiments/        un script por experimento (exp01 ... exp05)
scripts/            utilidades (verificación de GPU)
notebooks/          lanzador de Colab y análisis
splits/             particiones congeladas con hash (en git)
resultados/         config, entorno y métricas de cada corrida + resultados.csv (en git)
tests/              pruebas (no fuga entre particiones, paridad Keras ↔ TFLite, etc.)
data/, outputs/     datasets y artefactos pesados (fuera de git)
```

Cada corrida crea `resultados/<exp>/<id>/` con `config.yaml`, `entorno.json` (versiones, GPU y
commit) y `metricas.json`. Los modelos y predicciones de la corrida quedan en
`outputs/<exp>/<id>/`. `resultados/resultados.csv` se regenera con todas las corridas
(`python -m melanoma.runs`) y es la tabla del capítulo 6.

## Entorno

Python 3.12. Hay tres entornos, cada uno con un papel distinto.

**Contenedor de desarrollo (sin GPU).** Aquí se escribe el código y se corren EXP-01, EXP-05 y las
pruebas. El entorno se crea con [uv](https://docs.astral.sh/uv/):

```bash
uv venv --python 3.12
uv pip install -e ".[tf,litert,dev]"
.venv/bin/python -m pytest
```

**PC con RTX 5060 (entrenamiento), con Docker Desktop y `--gpus all`.** TensorFlow no usa la GPU
en Windows nativo desde la 2.10. La rueda de PyPI de TF 2.21 está compilada con CUDA 12.5 para
`sm_60` a `sm_89` (más PTX `compute_90`), sin kernels para Blackwell (`sm_120`), lo que es
coherente con que la imagen `tensorflow/tensorflow:latest-gpu` no vea la 5060. Desde la carpeta
del repo, en PowerShell:

```powershell
# Plan A: TensorFlow de NVIDIA (NGC 25.02, CUDA 12.8, soporta Blackwell)
docker run --gpus all --rm -it --shm-size=4g -v "${PWD}:/workspace" -w /workspace `
  nvcr.io/nvidia/tensorflow:25.02-tf2-py3 `
  python scripts/verificar_gpu.py --backend tensorflow

# Plan B: Keras 3 sobre PyTorch para entrenar; TensorFlow (CPU) solo para exportar el .tflite
docker run --gpus all --rm -it --shm-size=4g -v "${PWD}:/workspace" -w /workspace `
  pytorch/pytorch:2.14.0-cuda13.0-cudnn9-runtime `
  bash -c "pip install keras && python scripts/verificar_gpu.py --backend torch"
```

Para entrenar se usa el TensorFlow o el PyTorch que ya trae la imagen. El paquete del repo se
instala fijando el numpy de la imagen, para que pip no lo reemplace:

```bash
pip install -e . "numpy==$(python -c 'import numpy; print(numpy.__version__)')"
```

Si el repo está en una carpeta de Windows (`C:\...`), leer miles de imágenes a través del volumen
montado es lento: conviene tenerlo en el sistema de archivos de WSL o en un volumen de Docker.

**Colab**, como respaldo (el lanzador irá en `notebooks/`).

## Verificación de la GPU

`scripts/verificar_gpu.py` prueba cada backend en un subproceso aparte:

- que vea la GPU y si trae kernels nativos para su arquitectura (la 5060 es `sm_120`);
- que un matmul en GPU coincida con el de CPU;
- que Keras entrene unos pasos de MobileNetV3-Large con precisión mixta. En TensorFlow lo prueba
  con y sin XLA.

Al final da un veredicto (plan A, plan B o ninguno) y guarda el reporte en `resultados/entorno/`.
Si TensorFlow no trae kernels para `sm_120`, CUDA compila PTX la primera vez, lo que puede tardar
mucho. El script sube `CUDA_CACHE_MAXSIZE` para que esa compilación quede en caché; en Docker hay
que montar además un volumen en `/root/.nv` para no perderla al cerrar el contenedor.

## Datasets

Van en `data/` (fuera de git):

```
data/ham10000/HAM10000_metadata.csv
data/ham10000/images/            # ISIC_xxxxxxx.jpg
data/<isic>/...                  # año por confirmar
```

HAM10000: 10,015 imágenes en 7 clases. Si el ISIC es 2019, ya incluye las imágenes de HAM10000:
se deduplican por id de imagen antes de particionar.

## Experimentos

Se ejecutan en este orden. Cada uno lee su YAML de `configs/`.

| Orden | Experimento | Decisión que produce | Estado |
|---|---|---|---|
| 1 | EXP-01 Partición sin fuga | Test fijo (15%) + 5 folds por `lesion_id`, congelados en `splits/` | pendiente |
| 2 | EXP-02 Arquitecturas | {MobileNetV2, MobileNetV3-Large} × {cabeza densa, Random Forest} | pendiente |
| 3 | EXP-03 Desbalance | Sin balanceo, pesos de clase, sobremuestreo o focal loss | pendiente |
| 4 | EXP-05 Conversión a `.tflite` | Formato de cuantización, tamaño y latencia en CPU (2 hilos) | pendiente |
| 5 | EXP-04 Calibración y umbral | Probabilidad calibrada, umbral con recall ≥ 90%, banda de confianza baja | pendiente |

Reglas del protocolo:

- EXP-02 y EXP-03 se comparan con los 5 folds (media ± desviación); el candidato se elige por AUC-ROC.
- El test se usa una sola vez, al final de EXP-04.
- Siempre se reportan Accuracy, Precision, Recall, F1, AUC-ROC, PR-AUC, especificidad y matriz de
  confusión, con IC 95% por bootstrap. El recall de melanoma ≥ 90% en el umbral operativo es
  obligatorio. El F1 se reporta, pero no es meta.
