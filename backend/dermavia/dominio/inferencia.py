"""Módulo Inferencia (HU18, HU19): predicción preliminar de las dos fotos del caso.

Usa el artefacto versionado que publica el entorno de experimentación (registro de EXP-04): el
`.tflite` de la fusión de dos fotos en float16 y `artefacto.json`, con la calibración isotónica,
el umbral operativo y el sha256 del modelo. La versión activa la indica la configuración del
servicio, así que cambiar de modelo no requiere cambiar ni recompilar el código (RNF-13).

El preprocesamiento es el de `melanoma.serving` (Pillow + LiteRT), el mismo con el que EXP-04
fijó el umbral: EXP-05 mostró que leer las fotos con otra biblioteca hace cambiar de clase a
algunas lesiones, así que el backend importa ese código en vez de reescribirlo.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from .errores import ImagenInvalida
from .modelos import ClaseLesion, Prediccion
from .puertos import Reloj


class ErrorArtefacto(RuntimeError):
    """El artefacto publicado no es válido (sha256 distinto, campos faltantes...)."""


@dataclass(frozen=True)
class Artefacto:
    version: str
    sha256: str
    image_size: int
    umbral: float
    calibracion_x: tuple[float, ...]
    calibracion_y: tuple[float, ...]
    linea_alerta: float
    modelo: bytes

    @classmethod
    def desde_archivos(cls, artefacto_json: bytes, modelo: bytes) -> Artefacto:
        meta = json.loads(artefacto_json)
        try:
            calibracion = meta["calibration"]
            if calibracion["method"] != "isotonic":
                raise ErrorArtefacto(f"Calibración no soportada: {calibracion['method']}")
            if list(meta["inputs"]) != ["view_a", "view_b"]:
                raise ErrorArtefacto("El backend espera el modelo de dos fotos (view_a, view_b).")
            artefacto = cls(
                version=str(meta["version"]),
                sha256=str(meta["sha256"]),
                image_size=int(meta["image_size"]),
                umbral=float(meta["threshold"]),
                calibracion_x=tuple(float(v) for v in calibracion["x"]),
                calibracion_y=tuple(float(v) for v in calibracion["y"]),
                linea_alerta=float(meta["calibrated_threshold"]),
                modelo=modelo,
            )
        except KeyError as falta:
            raise ErrorArtefacto(f"Falta el campo {falta} en artefacto.json") from None
        real = hashlib.sha256(modelo).hexdigest()
        if real != artefacto.sha256:
            raise ErrorArtefacto(
                f"El sha256 del modelo ({real[:12]}…) no coincide con artefacto.json "
                f"({artefacto.sha256[:12]}…)")
        if len(artefacto.calibracion_x) != len(artefacto.calibracion_y):
            raise ErrorArtefacto("La calibración tiene x e y de distinto largo.")
        return artefacto

    def calibrar(self, salida: float) -> float:
        """Igual que `melanoma.calibration.apply` con el método isotónico."""
        return float(np.interp(salida, self.calibracion_x, self.calibracion_y))

    def clase(self, salida: float) -> ClaseLesion:
        """La regla del registro de EXP-04: con la salida sin calibrar, nunca con la calibrada."""
        return ClaseLesion.MELANOMA if salida >= self.umbral else ClaseLesion.NO_MELANOMA


class Motor(Protocol):
    """Salida sin calibrar del modelo para las dos fotos (bytes JPEG/PNG) de un caso."""

    def salida(self, foto_a: bytes, foto_b: bytes) -> float: ...


class MotorLiteRT:
    """`melanoma.serving` con un candado: el intérprete de LiteRT no admite hilos simultáneos.

    Decodificar y redimensionar las fotos queda fuera del candado, así que con concurrencia 4 en
    Cloud Run solo se serializa la inferencia, que tarda unos 7 ms por caso (EXP-05).
    """

    def __init__(self, artefacto: Artefacto, hilos: int = 2):
        from melanoma.serving import TFLiteClassifier

        self._image_size = artefacto.image_size
        self._clasificador = TFLiteClassifier(artefacto.modelo, num_threads=hilos)
        if self._clasificador.n_inputs != 2:
            raise ErrorArtefacto("El modelo publicado no tiene dos entradas.")
        self._candado = threading.Lock()

    def salida(self, foto_a: bytes, foto_b: bytes) -> float:
        from melanoma.serving import preprocess

        try:
            a = preprocess(foto_a, self._image_size)
            b = preprocess(foto_b, self._image_size)
        except Exception as error:  # Pillow lanza varios tipos según el formato
            raise ImagenInvalida() from error
        with self._candado:
            return self._clasificador.predict_case(a, b)[0]


class ModuloInferencia:
    def __init__(self, cargar_artefacto: Callable[[], Artefacto], reloj: Reloj,
                 crear_motor: Callable[[Artefacto], Motor] = MotorLiteRT):
        self._cargar_artefacto = cargar_artefacto
        self._crear_motor = crear_motor
        self._reloj = reloj
        self._artefacto: Artefacto | None = None
        self._motor: Motor | None = None
        self._candado = threading.Lock()

    def calentar(self) -> Artefacto:
        """Descarga y carga el artefacto (una vez por instancia de Cloud Run)."""
        with self._candado:
            if self._artefacto is None:
                artefacto = self._cargar_artefacto()
                self._motor = self._crear_motor(artefacto)
                self._artefacto = artefacto
            return self._artefacto

    @property
    def version(self) -> str | None:
        return self._artefacto.version if self._artefacto else None

    def predecir(self, foto_a: bytes, foto_b: bytes) -> Prediccion:
        artefacto = self.calentar()
        assert self._motor is not None
        inicio = time.perf_counter()
        salida = float(self._motor.salida(foto_a, foto_b))
        latencia_ms = (time.perf_counter() - inicio) * 1000
        return Prediccion(
            probabilidad_malignidad=artefacto.calibrar(salida),
            clase_predicha=artefacto.clase(salida),
            salida_modelo=salida,
            umbral_operativo=artefacto.umbral,
            linea_alerta=artefacto.linea_alerta,
            version_modelo=artefacto.version,
            sha256_modelo=artefacto.sha256,
            fecha_inferencia=self._reloj.ahora(),
            latencia_ms=round(latencia_ms, 2),
        )
