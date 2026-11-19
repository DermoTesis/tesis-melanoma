"""Servidor local, sin Google Cloud: `python -m dermavia.local [--puerto 8080]`.

Todo queda en memoria (se pierde al cerrar), las fotos se guardan en `.almacen-local/` y el
modelo se lee de `outputs/exp04/20261004T172732Z_registro/` (o de `DERMAVIA_MODELO_URI`). En vez
de un ID token de Firebase se usa `Authorization: Bearer dev:<uid>` con estas cuentas:

| uid | Rol |
|---|---|
| `admin-dev` | administrador |
| `especialista-dev` | especialista, con el alcance ya aceptado |
| `especialista-nuevo` | especialista que todavía no acepta el alcance |

Las tareas de Cloud Scheduler se llaman con `Authorization: Bearer dev-tareas`.
"""

from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime

from .contenedor import Contenedor
from .dominio.modelos import EstadoCuenta, Rol, Usuario

ESTABLECIMIENTO = "Hospital de demostración"


def sembrar(contenedor: Contenedor) -> None:
    usuarios = contenedor.identidad._usuarios  # solo para la siembra local
    ahora = datetime.now(UTC)
    for usuario in (
        Usuario(uid="admin-dev", rol=Rol.ADMIN, dni="00000001", nombres="Admin Dermavía",
                correo="admin@dermavia.local", estado=EstadoCuenta.ACTIVO,
                establecimiento=ESTABLECIMIENTO, acceso_clinico=False),
        Usuario(uid="especialista-dev", rol=Rol.ESPECIALISTA, dni="00000002",
                nombres="Dra. Especialista Demo", correo="especialista@dermavia.local",
                estado=EstadoCuenta.ACTIVO, establecimiento=ESTABLECIMIENTO,
                numero_colegiatura="12345", fecha_verificacion=ahora,
                fecha_aceptacion_terminos=ahora),
        Usuario(uid="especialista-nuevo", rol=Rol.ESPECIALISTA, dni="00000003",
                nombres="Dr. Especialista Nuevo", correo="nuevo@dermavia.local",
                estado=EstadoCuenta.PENDIENTE_ACTIVACION, establecimiento=ESTABLECIMIENTO,
                numero_colegiatura="54321", fecha_verificacion=ahora),
    ):
        usuarios.guardar(usuario)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--puerto", type=int, default=8080)
    args = parser.parse_args()

    os.environ["DERMAVIA_ENTORNO"] = "local"
    os.environ.setdefault("DERMAVIA_URL_BASE", f"http://{args.host}:{args.puerto}")

    import uvicorn

    from .config import Configuracion
    from .contenedor import construir
    from .infraestructura.registro import configurar_logging
    from .main import create_app

    configurar_logging()
    contenedor = construir(Configuracion.desde_entorno())
    sembrar(contenedor)
    uvicorn.run(create_app(contenedor), host=args.host, port=args.puerto, log_config=None)


if __name__ == "__main__":
    main()
