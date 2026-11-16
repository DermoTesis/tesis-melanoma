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
experiments/        un script por experimento (exp01 ... exp11)
scripts/            verificación de GPU y lanzador en la imagen de NVIDIA
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
coherente con que la imagen `tensorflow/tensorflow:latest-gpu` no vea la 5060. La imagen de NVIDIA
`nvcr.io/nvidia/tensorflow:25.02-tf2-py3` (TF 2.17, CUDA 12.8) sí la ve.

El repo vive en el volumen de Docker del contenedor de desarrollo, no en una carpeta de Windows,
así que se monta ese volumen (solo la carpeta del repo) y se corre como el usuario del contenedor
(uid 1000), para que los archivos nuevos no queden a nombre de root. En PowerShell, una vez por
sesión, con el id del contenedor de desarrollo (`docker ps`):

```powershell
$vol = docker inspect <id-del-contenedor> --format '{{range .Mounts}}{{if eq .Destination `/workspaces`}}{{.Name}}{{end}}{{end}}'
$gpu = "run", "--gpus", "all", "--rm", "-it", "--ipc=host", "--ulimit", "memlock=-1",
  "--ulimit", "stack=67108864", "--user", "1000:1000", "-e", "HOME=/tmp",
  "--mount", "type=volume,src=$vol,dst=/workspace,volume-subpath=tesis-melanoma", "-w", "/workspace"
```

Luego:

```powershell
# Plan A: TensorFlow de NVIDIA
docker @gpu nvcr.io/nvidia/tensorflow:25.02-tf2-py3 python scripts/verificar_gpu.py --backend tensorflow
docker @gpu nvcr.io/nvidia/tensorflow:25.02-tf2-py3 bash scripts/gpu.sh experiments/exp02_mobilenetv3.py

# Plan B: Keras 3 sobre PyTorch para entrenar; TensorFlow (CPU) solo para exportar el .tflite
docker @gpu pytorch/pytorch:2.14.0-cuda13.0-cudnn9-runtime `
  bash -c "pip install --user keras && python scripts/verificar_gpu.py --backend torch"
```

`scripts/gpu.sh` crea la primera vez `.venv-gpu/` (fuera de git) con el TensorFlow de la imagen y
el paquete del repo, sin reemplazar el numpy de la imagen.

**Colab**, como respaldo (el lanzador irá en `notebooks/`).

## Verificación de la GPU

`scripts/verificar_gpu.py` prueba cada backend en un subproceso aparte:

- que vea la GPU y si trae kernels nativos para su arquitectura (la 5060 es `sm_120`);
- que un matmul en GPU coincida con el de CPU;
- que Keras entrene unos pasos de MobileNetV3-Large con precisión mixta. En TensorFlow lo prueba
  con y sin XLA.

Al final da un veredicto (plan A, plan B o ninguno) y guarda el reporte en `resultados/entorno/`.
Su velocidad (con `train_on_batch`) no es representativa. Para medir la velocidad real está
`scripts/benchmark_gpu.py`: en la RTX 5060, MobileNetV3-Large entrena a ~150 img/s sin XLA y a
~810 img/s con precisión mixta y XLA, por eso el entrenamiento usa XLA (`training.jit_compile`).
Si TensorFlow no trae kernels para `sm_120`, CUDA compila PTX la primera vez, lo que puede tardar
mucho. El script sube `CUDA_CACHE_MAXSIZE` para que esa compilación quede en caché; en Docker hay
que montar además un volumen en `/root/.nv` para no perderla al cerrar el contenedor.

## Dataset

Solo HAM10000 (Tschandl et al., 2018), de Harvard Dataverse (doi:10.7910/DVN/DBW86T, licencia
CC BY-NC 4.0). Tiene 10,015 imágenes de 7,470 lesiones en 7 clases. Melanoma: 1,113 imágenes de
614 lesiones, todas confirmadas por histopatología. Va en `data/` (fuera de git):

```
data/ham10000/HAM10000_metadata.csv   # su md5 está fijado en configs/base.yaml
data/ham10000/images/                 # ISIC_xxxxxxx.jpg
```

Para descargarlo (~2.6 GB):

```bash
B=https://dataverse.harvard.edu/api/access/datafile
mkdir -p data/ham10000/images && cd data/ham10000
curl -L -o HAM10000_metadata.csv "$B/4338392?format=original"
curl -L -o part_1.zip "$B/3172585" && curl -L -o part_2.zip "$B/3172584"
unzip -q part_1.zip -d images && unzip -q part_2.zip -d images && rm part_1.zip part_2.zip
```

## Experimentos

Se ejecutan en este orden. Cada uno lee su YAML de `configs/`.

| Orden | Experimento | Decisión que produce | Comando |
|---|---|---|---|
| 1 | EXP-01 Partición sin fuga | Test fijo (15%) + 5 folds por `lesion_id`, congelados en `splits/` | `python experiments/exp01_particion.py` |
| 2 | EXP-02 MobileNetV3-Large | Línea base de extremo a extremo con una foto, en los 5 folds | `bash scripts/gpu.sh experiments/exp02_mobilenetv3.py` |
| 3 | EXP-03 Desbalance | Sin balanceo, pesos de clase, sobremuestreo o focal loss (comparación pareada con la línea base) | `bash scripts/gpu.sh experiments/exp03_desbalance.py` |
| 4 | EXP-05 Conversión a `.tflite` | Formato de cuantización, tamaño, latencia en CPU (2 núcleos) y pérdida de AUC; corre en CPU | `python experiments/exp05_tflite.py` |
| 5 | EXP-06 Una foto vs. dos fotos | Fusión aprendida frente a una foto y al promedio fijo, sobre las mismas lesiones con 2+ fotos, y robustez a una foto mala (aporte del trabajo) | `bash scripts/gpu.sh experiments/exp06_dos_fotos.py` |
| 5b | EXP-07 Datos del paciente | Fusión de dos fotos más edad, sexo y zona del cuerpo, comparada lesión por lesión con EXP-06, para bajar las falsas alarmas sin perder sensibilidad | `bash scripts/gpu.sh experiments/exp06_dos_fotos.py --config configs/exp07_datos_paciente.yaml` |
| 5c | EXP-08 Funciones de pérdida | BCE, focal loss (γ = 2, α = 0.25) y asymmetric loss (γ− = 4, m = 0.05) en una foto y en la fusión, con 3 semillas; decide la fusión (criterio en el docstring). Unas 12-14 h, reanudable con `--set resume=exp08/<id>` | `bash scripts/gpu.sh experiments/exp08_perdidas.py` |
| 6 | EXP-04 Modelo final, calibración y umbral | Modelo con todo train+val (GPU), calibración y umbral con margen registrados antes del test, y la única evaluación del test | `bash scripts/gpu.sh experiments/exp04_modelo_final.py`, luego `python experiments/exp04_evaluacion.py` (ver su docstring) |
| 7 | EXP-09 Dejar fuera una fuente | Modelo de una foto entrenado con 3 fuentes de HAM10000 y evaluado en la cuarta (solo train+val), frente a la AUC fuera de fold dentro de esa fuente. Unas 4 entrenadas, reanudable con `--set resume=exp09/<id>` | `bash scripts/gpu.sh experiments/exp09_fuentes.py` |
| 7b | EXP-10 Una foto entrenada con fotos degradadas | Ablación de la H3: el promedio de un modelo de una foto entrenado con las degradaciones de la fusión, frente a la fusión de EXP-06, sobre los mismos pares. 5 folds, reanudable | `bash scripts/gpu.sh experiments/exp10_una_foto_degradada.py` |
| 7c | EXP-11 Backbones más grandes | EfficientNetV2-B0 y -S en el modelo de una foto (5 folds cada uno) frente a MobileNetV3; luego la latencia del `.tflite` float16 en CPU | `bash scripts/gpu.sh experiments/exp11_backbones.py`, luego (en el contenedor de desarrollo) `python experiments/exp11_backbones.py --set stage=latencia --set source_run=exp11/<id>` |

EXP-06 va antes de EXP-04 para que la calibración y la única evaluación en el test usen el
modelo definitivo. EXP-08 (pedido del asesor) se agregó después de los pasos 1 y 2 de EXP-04: si
adopta una pérdida, esos dos pasos se rehacen con ella antes de tocar el test.
El test se evaluó el 2026-11-14. EXP-09 a EXP-11 se agregaron después para el short paper: son
descriptivos, solo usan train+val y no cambian el modelo registrado.

Las matrices de confusión de cada corrida se generan aparte, en CPU, desde sus predicciones:
`python scripts/matriz_confusion.py resultados/exp02/<corrida>` (necesita `matplotlib`, extra
`plots`).

Reglas del protocolo:

- EXP-02, EXP-03 y EXP-06 se comparan con los 5 folds (media ± desviación) y con todas las
  predicciones fuera de fold juntas; el candidato se elige por AUC-ROC.
- El test se usa una sola vez, al final de EXP-04.
- Siempre se reportan Accuracy, Precision, Recall, F1, AUC-ROC, PR-AUC, especificidad y matriz de
  confusión, con IC 95% por bootstrap. El recall de melanoma ≥ 90% en el umbral operativo es
  obligatorio. El F1 se reporta, pero no es meta.

## Licencia

El código de este repositorio se publica con la licencia MIT (ver `LICENSE`). HAM10000 no se
incluye en el repositorio; lo rige su propia licencia, CC BY-NC 4.0, que no permite el uso
comercial de las imágenes.
