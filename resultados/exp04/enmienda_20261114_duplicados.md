# EXP-04: enmienda previa a la evaluación del test (2026-11-14)

Se escribió y se commiteó **antes** de correr el paso 3. No cambia el registro
(`20261004T172732Z_registro`, commit 0553fae), ni el modelo, ni los umbrales, ni las hipótesis H1–H3.

## Hallazgo

Abhishek, Jain y Hamarneh (Sci. Data 12:196, 2025) publican 18 pares de imágenes duplicadas de HAM10000
con distinto `lesion_id`, más 2 pares casi duplicados que podrían ser la misma lesión en otra visita.
Los detectaron con fastdup y los revisaron a mano. La lista es el CSV
`newly_discovered_duplicates.csv` del repo kakumarabhishek/Corrected-Skin-Image-Datasets, commit
ac655ac. Como nuestra partición agrupa por `lesion_id` (EXP-01), no los detecta.

El cruce con `splits/ham10000_v1` está en `duplicados_abhishek2025.csv`:

- **4 pares cruzan entrenamiento y test** (pares 3, 4, 5 y 9). Las lesiones del test afectadas son
  HAM_0003816 (nv), HAM_0007604 (bkl), HAM_0001310 (bkl) y HAM_0000140 (nv):
  - todas son benignas y tienen una sola foto, así que solo están en la población secundaria;
  - el modelo final (entrenado con todo train+val) vio su duplicado.
- **1 par tiene las dos imágenes en el test** (par 18). No hay fuga, pero son dos "lesiones" que en
  realidad podrían ser una.
- **11 pares cruzan folds de validación.** Afectan un poco las estimaciones fuera de fold de EXP-02 a
  EXP-08: son 22 de 8,512 imágenes, y ninguna es melanoma.
- Ninguno de los 20 pares es melanoma, y ninguna lesión de la población principal (las 294 del test
  con 2 o más fotos) está afectada. Por eso H1, H2 y H3 no cambian.

Una búsqueda propia, por correlación de píxeles con volteos y rotaciones de 180°, confirmó el par 9
(correlación 0.9986 a 32 × 24 px) y no encontró otros pares que crucen entrenamiento y test.

## Qué se agrega al análisis (decidido antes de ver el test)

- La población principal y las hipótesis H1–H3 se evalúan **tal como se registraron**.
- La población secundaria se reporta como se registró y, además, como **análisis de sensibilidad
  sin las 4 lesiones del test** que tienen un duplicado en entrenamiento. Se calcula con
  `predicciones_test_todas.csv`, con el mismo umbral y el mismo bootstrap.
- En el paper se declara que las estimaciones fuera de fold incluyen 11 pares duplicados entre folds.
