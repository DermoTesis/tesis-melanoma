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
    """Probabilidad de melanoma de una foto ya preprocesada, con el intérprete de LiteRT.

    Usa XNNPACK, el acelerador de CPU que LiteRT activa por defecto. Si no puede preparar el
    modelo (pasa con el int8 de MobileNetV3), usa los kernels normales; `xnnpack` dice cuál quedó.
    """

    def __init__(self, model: str | Path | bytes, num_threads: int = 2):
        from ai_edge_litert.interpreter import Interpreter, OpResolverType

        source = {"model_content": model} if isinstance(model, bytes) else {"model_path": str(model)}
        try:
            self.interpreter = Interpreter(**source, num_threads=num_threads)
            self.interpreter.allocate_tensors()
            self.xnnpack = True
        except RuntimeError:
            self.interpreter = Interpreter(
                **source, num_threads=num_threads,
                experimental_op_resolver_type=OpResolverType.BUILTIN_WITHOUT_DEFAULT_DELEGATES)
            self.interpreter.allocate_tensors()
            self.xnnpack = False
        self._input = self.interpreter.get_input_details()[0]["index"]
        self._output = self.interpreter.get_output_details()[0]["index"]

    def predict_one(self, image: np.ndarray) -> float:
        self.interpreter.set_tensor(self._input, image[None].astype(np.float32))
        self.interpreter.invoke()
        return float(self.interpreter.get_tensor(self._output).ravel()[0])

    def predict(self, images: Iterable[np.ndarray]) -> np.ndarray:
        return np.array([self.predict_one(image) for image in images])
