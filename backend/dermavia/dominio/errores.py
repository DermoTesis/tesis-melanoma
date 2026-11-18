"""Errores de negocio con un mensaje apto para mostrarse al médico tal cual (RNF-16).

Cada error trae un `codigo` estable que la app usa para elegir la pantalla o el aviso. Los
códigos coinciden con los de `AppException` en la app (`permission-denied`, `consent-required`,
`validation-required`), para que el cambio del backend simulado al real no toque la UI.
"""

from __future__ import annotations


class ErrorDominio(Exception):
    codigo = "error"
    estado_http = 400
    mensaje_por_defecto = "No se pudo completar la operación."

    def __init__(self, mensaje: str | None = None):
        self.mensaje = mensaje or self.mensaje_por_defecto
        super().__init__(self.mensaje)


class NoAutenticado(ErrorDominio):
    codigo = "unauthenticated"
    estado_http = 401
    mensaje_por_defecto = "Tu sesión expiró. Inicia sesión otra vez."


class PermisoDenegado(ErrorDominio):
    codigo = "permission-denied"
    estado_http = 403
    mensaje_por_defecto = "No tienes permisos para realizar esta acción."


class NoEncontrado(ErrorDominio):
    codigo = "not-found"
    estado_http = 404
    mensaje_por_defecto = "No se encontró el registro solicitado."


class DatosInvalidos(ErrorDominio):
    codigo = "invalid-argument"
    estado_http = 422
    mensaje_por_defecto = "Revisa los datos ingresados."


class Conflicto(ErrorDominio):
    codigo = "already-exists"
    estado_http = 409
    mensaje_por_defecto = "El registro ya existe."


class EstadoInvalido(ErrorDominio):
    codigo = "invalid-state"
    estado_http = 409
    mensaje_por_defecto = "El caso no está en un estado que permita esta acción."


class ConsentimientoRequerido(ErrorDominio):
    codigo = "consent-required"
    estado_http = 409
    mensaje_por_defecto = (
        "El paciente no tiene un consentimiento informado vigente. "
        "Regístralo antes de capturar imágenes."
    )


class ValidacionRequerida(ErrorDominio):
    codigo = "validation-required"
    estado_http = 409
    mensaje_por_defecto = (
        "El caso no puede cerrarse ni generar su informe sin una validación médica registrada."
    )


class ImagenInvalida(ErrorDominio):
    """La foto no se puede leer como imagen: reintentar el análisis no lo arregla."""

    codigo = "invalid-image"
    estado_http = 422
    mensaje_por_defecto = "Una de las fotos no se pudo leer. Vuelve a cargarla."
