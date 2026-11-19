"""Backend de Dermavía: monolito modular desplegado como un único servicio en Cloud Run.

Sigue la sección 5.2 de la memoria (Tabla 6): una capa de presentación (API REST que valida el
ID token de Firebase y el rol en cada solicitud), ocho módulos de dominio que se comunican solo
por sus interfaces públicas y una capa de infraestructura con los servicios gestionados
(Firestore, Cloud Storage, Firebase Authentication y Cloud Messaging, Cloud Logging).
"""

__version__ = "0.1.0"
