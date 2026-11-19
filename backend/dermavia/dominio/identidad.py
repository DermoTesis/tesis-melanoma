"""Módulo Identidad: cuentas, roles y aceptación del alcance de apoyo diagnóstico.

Firebase Authentication guarda las credenciales y emite los ID token; este módulo guarda el
perfil (colección `usuarios`) y decide los permisos. El rol se copia como custom claim, pero
los permisos se leen siempre del perfil, para que revocar el acceso clínico tenga efecto en la
siguiente solicitud y no recién cuando el token se renueve.

Flujo de alta (Figura 13 de la memoria): el administrador verifica la colegiatura fuera del
sistema y registra al especialista; la cuenta se crea sin contraseña y el especialista la activa
definiendo su contraseña con el flujo de recuperación de Firebase (RF-01.2). La primera solicitud
autenticada marca la cuenta como activa.
"""

from __future__ import annotations

import re
from dataclasses import replace

from .auditoria import ModuloAuditoria
from .errores import Conflicto, DatosInvalidos, NoEncontrado, PermisoDenegado
from .modelos import EstadoCuenta, Rol, TipoEvento, Usuario
from .puertos import Cuentas, Reloj, RepoUsuarios

_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DNI = re.compile(r"^\d{8}$")
_CMP = re.compile(r"^\d{3,6}$")
MAX_TOKENS_DISPOSITIVO = 5


class ModuloIdentidad:
    def __init__(self, usuarios: RepoUsuarios, cuentas: Cuentas, auditoria: ModuloAuditoria,
                 reloj: Reloj):
        self._usuarios = usuarios
        self._cuentas = cuentas
        self._auditoria = auditoria
        self._reloj = reloj

    # --- Autorización (la usa la capa de presentación en cada solicitud) ---

    def autenticado(self, uid: str) -> Usuario:
        """Perfil del dueño de un ID token ya verificado. La primera vez, activa la cuenta."""
        usuario = self._usuarios.obtener(uid)
        if usuario is None:
            # Cuenta de Firebase sin perfil: no la creó un administrador.
            raise PermisoDenegado("Tu cuenta no está habilitada en Dermavía.")
        if usuario.estado == EstadoCuenta.PENDIENTE_ACTIVACION:
            usuario = replace(usuario, estado=EstadoCuenta.ACTIVO)
            self._usuarios.guardar(usuario)
            self._auditoria.registrar(TipoEvento.ACTIVACION_CUENTA, usuario.correo, usuario)
        return usuario

    def exigir_clinico(self, usuario: Usuario) -> Usuario:
        """Solo especialistas con acceso clínico y el alcance aceptado (RNF-03, RF-05.3)."""
        if not usuario.es_especialista or not usuario.acceso_clinico:
            raise PermisoDenegado("Tu cuenta no tiene acceso a funciones clínicas.")
        if usuario.fecha_aceptacion_terminos is None:
            raise PermisoDenegado(
                "Debes aceptar el alcance de apoyo diagnóstico antes de continuar.")
        return usuario

    def exigir_admin(self, usuario: Usuario) -> Usuario:
        if not usuario.es_admin:
            raise PermisoDenegado()
        return usuario

    # --- Operaciones ---

    def aceptar_terminos(self, usuario: Usuario) -> Usuario:
        """Aceptación fechada del alcance de apoyo diagnóstico (RF-05.3, RNF-06). Idempotente."""
        if usuario.fecha_aceptacion_terminos is not None:
            return usuario
        usuario = replace(usuario, fecha_aceptacion_terminos=self._reloj.ahora())
        self._usuarios.guardar(usuario)
        self._auditoria.registrar(TipoEvento.ACEPTACION_ALCANCE, usuario.correo, usuario)
        return usuario

    def alta_especialista(self, admin: Usuario, *, nombres: str, correo: str, dni: str,
                          numero_colegiatura: str, colegiatura_verificada: bool,
                          establecimiento: str | None = None) -> Usuario:
        self.exigir_admin(admin)
        nombres, correo = nombres.strip(), correo.strip().lower()
        dni, numero_colegiatura = dni.strip(), numero_colegiatura.strip()
        if not colegiatura_verificada:
            raise DatosInvalidos(
                "Verifica la colegiatura en el Colegio Médico antes de dar de alta la cuenta.")
        if not nombres:
            raise DatosInvalidos("Ingresa los nombres y apellidos.")
        if not _CORREO.match(correo):
            raise DatosInvalidos("Ingresa un correo válido.")
        if not _DNI.match(dni):
            raise DatosInvalidos("El DNI debe tener 8 dígitos.")
        if not _CMP.match(numero_colegiatura):
            raise DatosInvalidos("El número de colegiatura (CMP) no es válido.")
        if any(u.correo == correo for u in self._usuarios.listar()):
            raise Conflicto("Ya existe una cuenta con ese correo.")

        uid = self._cuentas.crear(correo, nombres)
        self._cuentas.fijar_rol(uid, Rol.ESPECIALISTA)
        usuario = Usuario(
            uid=uid,
            rol=Rol.ESPECIALISTA,
            dni=dni,
            nombres=nombres,
            correo=correo,
            estado=EstadoCuenta.PENDIENTE_ACTIVACION,
            establecimiento=(establecimiento or admin.establecimiento).strip(),
            numero_colegiatura=numero_colegiatura,
            colegiatura_verificada_por=admin.uid,
            fecha_verificacion=self._reloj.ahora(),
        )
        self._usuarios.guardar(usuario)
        self._auditoria.registrar(TipoEvento.ALTA_CUENTA, correo, admin,
                                  numero_colegiatura=numero_colegiatura)
        return usuario

    def cambiar_permisos(self, admin: Usuario, uid: str, *, rol: Rol | None = None,
                         acceso_clinico: bool | None = None) -> Usuario:
        self.exigir_admin(admin)
        usuario = self._usuarios.obtener(uid)
        if usuario is None:
            raise NoEncontrado("No se encontró el usuario.")
        if uid == admin.uid:
            raise DatosInvalidos("No puedes cambiar tus propios permisos.")
        nuevo = replace(
            usuario,
            rol=rol if rol is not None else usuario.rol,
            acceso_clinico=acceso_clinico if acceso_clinico is not None else usuario.acceso_clinico,
        )
        if nuevo == usuario:
            return usuario
        self._usuarios.guardar(nuevo)
        if nuevo.rol != usuario.rol:
            self._cuentas.fijar_rol(uid, nuevo.rol)
        if not nuevo.acceso_clinico or nuevo.rol != usuario.rol:
            self._cuentas.revocar_sesiones(uid)
        self._auditoria.registrar(TipoEvento.CAMBIO_PERMISOS, usuario.correo, admin,
                                  rol=nuevo.rol.value, acceso_clinico=nuevo.acceso_clinico)
        return nuevo

    def listar_usuarios(self, admin: Usuario) -> list[Usuario]:
        self.exigir_admin(admin)
        return sorted(self._usuarios.listar(), key=lambda u: u.nombres)

    def registrar_dispositivo(self, usuario: Usuario, token: str) -> Usuario:
        """Token de FCM del celular, para las alertas de casos vencidos (RF-04.5)."""
        token = token.strip()
        if not token:
            raise DatosInvalidos("El token del dispositivo está vacío.")
        actual = self._usuarios.obtener(usuario.uid) or usuario
        tokens = tuple(t for t in actual.tokens_dispositivo if t != token) + (token,)
        nuevo = replace(actual, tokens_dispositivo=tokens[-MAX_TOKENS_DISPOSITIVO:])
        self._usuarios.guardar(nuevo)
        return nuevo

    def obtener(self, uid: str) -> Usuario | None:
        """Interfaz para otros módulos (Informes, Notificaciones)."""
        return self._usuarios.obtener(uid)

    def quitar_tokens(self, uid: str, invalidos: list[str]) -> None:
        usuario = self._usuarios.obtener(uid)
        if usuario is None or not invalidos:
            return
        tokens = tuple(t for t in usuario.tokens_dispositivo if t not in invalidos)
        self._usuarios.guardar(replace(usuario, tokens_dispositivo=tokens))
