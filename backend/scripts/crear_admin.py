"""Crea la primera cuenta de administrador (las siguientes cuentas las da de alta un admin).

Crea el usuario en Firebase Authentication con el claim `rol=admin`, guarda su perfil en
Firestore y muestra el enlace para que defina su contraseña. Requiere credenciales de Google
Cloud con permisos sobre el proyecto (`gcloud auth application-default login`).

    GOOGLE_CLOUD_PROJECT=<proyecto> python scripts/crear_admin.py \
        --correo admin@hospital.gob.pe --nombres "Nombre Apellido" --dni 12345678 \
        --establecimiento "Hospital ..."
"""

from __future__ import annotations

import argparse
import os

from dermavia.dominio.modelos import EstadoCuenta, Rol, Usuario


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--correo", required=True)
    parser.add_argument("--nombres", required=True)
    parser.add_argument("--dni", required=True)
    parser.add_argument("--establecimiento", required=True)
    args = parser.parse_args()

    from firebase_admin import auth
    from google.cloud import firestore

    from dermavia.infraestructura.firebase import CuentasFirebase, iniciar_app
    from dermavia.infraestructura.firestore import RepoUsuariosFirestore

    proyecto = os.environ["GOOGLE_CLOUD_PROJECT"]
    app = iniciar_app(proyecto)
    cuentas = CuentasFirebase(app)
    correo = args.correo.strip().lower()
    uid = cuentas.crear(correo, args.nombres.strip())
    cuentas.fijar_rol(uid, Rol.ADMIN)
    RepoUsuariosFirestore(firestore.Client(project=proyecto)).guardar(Usuario(
        uid=uid, rol=Rol.ADMIN, dni=args.dni.strip(), nombres=args.nombres.strip(),
        correo=correo, estado=EstadoCuenta.PENDIENTE_ACTIVACION,
        establecimiento=args.establecimiento.strip(), acceso_clinico=False))
    print(f"Administrador creado (uid {uid}).")
    print("Enlace para definir la contraseña:")
    print(auth.generate_password_reset_link(correo, app=app))


if __name__ == "__main__":
    main()
