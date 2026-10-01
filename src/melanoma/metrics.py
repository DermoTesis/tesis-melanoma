"""Métricas: Accuracy, Precision, Recall, F1, AUC-ROC, PR-AUC, especificidad y matriz de confusión,
con IC 95% por bootstrap. Las usan EXP-02 en adelante.

El bootstrap remuestrea lesiones, no imágenes: las imágenes de una misma lesión están
correlacionadas (en HAM10000 los melanomas tienen 1.8 imágenes por lesión en promedio), así que
remuestrear imágenes daría intervalos demasiado estrechos."""
