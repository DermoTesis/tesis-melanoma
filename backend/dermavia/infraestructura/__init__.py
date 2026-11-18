"""Capa de infraestructura: adaptadores de los puertos del dominio.

- `memoria`: implementaciones en memoria, para las pruebas y el servidor local.
- `firestore`, `gcs`, `firebase`: Google Cloud (Firestore, Cloud Storage, Firebase Admin SDK).
- `modelo`: carga del artefacto versionado del modelo (directorio local o Cloud Storage).
- `registro`: registros estructurados en JSON para Cloud Logging.
"""
