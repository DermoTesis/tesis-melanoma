"""Datos: lectura de metadatos, unión y deduplicación de fuentes, particiones y tf.data.

- EXP-01: metadatos de HAM10000 y del ISIC, etiqueta binaria, deduplicación por id de imagen y
  partición por `lesion_id` (test fijo + StratifiedGroupKFold), congelada en `splits/` con hash.
- EXP-02 en adelante: pipeline de imágenes (lectura, redimensionado y aumento de datos).
"""
