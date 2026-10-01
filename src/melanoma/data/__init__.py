"""Datos: metadatos de HAM10000, partición sin fuga por lesión e imágenes con tf.data.

- `ham10000`: lectura y validación de los metadatos y etiqueta binaria (melanoma vs. el resto).
- `splits`: partición por `lesion_id` (test fijo + StratifiedGroupKFold), congelada con hash (EXP-01).
- `pipeline`: lectura, redimensionado y aumento de datos de las imágenes (EXP-02 en adelante).
"""
