"""Inferencia como en el backend (Cloud Run): Pillow para leer la foto y LiteRT para el modelo.

Es el código de referencia del módulo Inferencia (HU18) y el que mide EXP-05: decodificar la foto,
redimensionarla entera a `image_size` × `image_size` y pasarle los píxeles 0-255 al `.tflite`, que
trae su propio preprocesamiento. Solo usa numpy, Pillow y ai-edge-litert, sin TensorFlow, para que
la imagen del servicio sea liviana y arranque rápido.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Iterable

import numpy as np


def preprocess(data: bytes, image_size: int = 224) -> np.ndarray:
    """JPEG → uint8 (image_size, image_size, 3), como `load_image` en el entrenamiento.

    El bilineal de Pillow suaviza al reducir, igual que `tf.image.resize(..., antialias=True)`;
    EXP-05 mide cuánto cambian las predicciones por las pequeñas diferencias entre ambos.
    """
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        image = image.convert("RGB").resize((image_size, image_size), Image.Resampling.BILINEAR)
        return np.asarray(image, dtype=np.uint8)


class TFLiteClassifier:
    """Probabilidad de melanoma con el intérprete de LiteRT, de una o de dos fotos preprocesadas.

    El modelo de una foto tiene una entrada; el de dos fotos (EXP-06) tiene dos, `view_a` y
    `view_b`, en ese orden. `predict_case` clasifica un caso (panorámica y acercamiento) con
    cualquiera de los dos: el de una foto devuelve una probabilidad por foto.

    Usa XNNPACK, el acelerador de CPU que LiteRT activa por defecto. Si no puede preparar el
    modelo (pasa con el int8 de MobileNetV3), usa los kernels normales; `xnnpack` dice cuál quedó.
    """

    def __init__(self, model: str | Path | bytes, num_threads: int = 2):
        from ai_edge_litert.interpreter import Interpreter, OpResolverType

        source = {"model_content": model} if isinstance(model, bytes) else {"model_path": str(model)}
        try:
            self._load(Interpreter(**source, num_threads=num_threads))
            # XNNPACK a veces falla recién en la primera inferencia: se prueba aquí.
            self.predict_one(*[np.zeros(self._shape, np.float32)] * self.n_inputs)
            self.xnnpack = True
        except RuntimeError:
            self._load(Interpreter(
                **source, num_threads=num_threads,
                experimental_op_resolver_type=OpResolverType.BUILTIN_WITHOUT_DEFAULT_DELEGATES))
            self.xnnpack = False

    def _load(self, interpreter) -> None:
        self.interpreter = interpreter
        interpreter.allocate_tensors()
        inputs = sorted(interpreter.get_input_details(), key=lambda d: d["name"])
        self._inputs = [d["index"] for d in inputs]
        self._shape = tuple(inputs[0]["shape"][1:])
        self._output = interpreter.get_output_details()[0]["index"]

    @property
    def n_inputs(self) -> int:
        return len(self._inputs)

    def predict_one(self, *images: np.ndarray) -> float:
        """Una inferencia: una foto, o las dos del caso si el modelo es de dos fotos."""
        if len(images) != self.n_inputs:
            raise ValueError(f"El modelo espera {self.n_inputs} foto(s) y recibió {len(images)}")
        for index, image in zip(self._inputs, images):
            self.interpreter.set_tensor(index, image[None].astype(np.float32))
        self.interpreter.invoke()
        return float(self.interpreter.get_tensor(self._output).ravel()[0])

    def predict(self, items: Iterable[np.ndarray | tuple[np.ndarray, ...]]) -> np.ndarray:
        """Una probabilidad por elemento: una foto, o una tupla (A, B) con el modelo de dos fotos."""
        return np.array([self.predict_one(*item) if isinstance(item, tuple) else self.predict_one(item)
                         for item in items])

    def predict_case(self, a: np.ndarray, b: np.ndarray) -> list[float]:
        """Las dos fotos de un caso: una probabilidad con el modelo de dos fotos, dos con el de una."""
        if self.n_inputs == 2:
            return [self.predict_one(a, b)]
        return [self.predict_one(a), self.predict_one(b)]
