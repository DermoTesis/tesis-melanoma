# Imágenes para probar la app con el backend

Seis lesiones de la **partición de prueba** de HAM10000 (`splits/ham10000_v1`), con dos fotos
dermatoscópicas cada una. El modelo nunca las vio en el entrenamiento. Se descargan del
[ISIC Archive](https://www.isic-archive.com/) con `descargar_isic.py`.

Cada carpeta trae dos versiones de cada foto:

- `fotoN_ISIC_xxxxxxx.jpg`: la original, de 600×450.
- `fotoN_ISIC_xxxxxxx_1024.jpg`: ampliada a 1366×1024. **Estas son las que hay que cargar desde
  la galería**: el control de calidad de la app exige que el lado menor mida al menos 1024 px y
  rechaza las originales.

Carga la `foto1` como foto 1 y la `foto2` como foto 2. El orden no cambia el resultado: el
modelo es simétrico (comprobado con las seis lesiones).

## Resultado esperado

Medido el 2026-11-19 con el backend local (`backend/model/`, artefacto
`20261004T172732Z_registro`) sobre las fotos ampliadas:

| Carpeta | Diagnóstico real | Lo que debe mostrar la app |
|---|---|---|
| `1_HAM_0001974_melanoma_alto` | melanoma | Posible melanoma · riesgo 75 % (riesgo alto) |
| `2_HAM_0007538_melanoma_intermedio` | melanoma | Posible melanoma · riesgo 58 % (riesgo intermedio) |
| `3_HAM_0003176_melanoma_bajo` | melanoma | Posible melanoma · riesgo 18 % (riesgo bajo) |
| `4_HAM_0001726_melanoma_falso_negativo` | melanoma | Sin alerta de melanoma · riesgo 7 % |
| `5_HAM_0002701_nevus_falso_positivo` | nevus | Posible melanoma · riesgo 58 % |
| `6_HAM_0000181_nevus_sin_alerta` | nevus | Sin alerta de melanoma · riesgo 3 % |

- **Carpeta 4:** su salida sin calibrar (0.012) queda apenas bajo el umbral (0.0138), así que es
  un falso negativo. Sirve para ver el escalón del 7 %: otra lesión con el mismo 7 % podría tener
  alerta.
- **Carpeta 5:** es un falso positivo, esperable con un umbral pensado para no dejar pasar
  melanomas (especificidad ~36 %).
- **Diferencias con el experimento:** la salida sin calibrar difiere un poco de
  `resultados/exp04/20261114T005335Z_evaluacion-test/predicciones_test.csv`, también con las
  fotos originales (la mayor, en la carpeta 3: 0.20 frente a 0.16). Aun así, la clase y el riesgo
  mostrado coinciden en las seis, porque la calibración agrupa las salidas en escalones.
- **Elección de las lesiones:** se descartaron las que la app rechaza por enfoque, que con estas
  fotos ampliadas son sobre todo las del origen `rosendahl`.

## Cómo pasarlas al teléfono

Conecta el teléfono por USB en modo "Transferencia de archivos" y copia las fotos `_1024.jpg` a
`Pictures` o `DCIM` desde el Explorador de Windows. También sirve `adb push`, pero la galería
puede tardar en mostrar los archivos copiados así.

## Volver a descargarlas

Las fotos no se versionan (licencia CC BY-NC 4.0, créditos en `creditos.txt`). Desde la raíz del
repositorio, con el entorno del backend:

```powershell
backend\.venv\Scripts\python.exe -I imagenes_prueba\descargar_isic.py imagenes_prueba
```
