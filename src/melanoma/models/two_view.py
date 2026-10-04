"""Clasificador de dos fotos de la misma lesión (EXP-06, HU36): fusión aprendida de las vistas.

Las dos fotos pasan por el mismo MobileNetV3-Large (pesos compartidos). Una red chica le da un
puntaje a las características de cada foto y un softmax entre las dos lo convierte en pesos: la
fusión es el promedio ponderado de las características, y la cabeza densa da la probabilidad.

- Es simétrico: f(A, B) = f(B, A), así que no hace falta saber cuál foto es la panorámica (en
  HAM10000 no está indicado).
- Con la misma foto dos veces los pesos son 0.5 y 0.5 y la fusión es esa foto: es el respaldo de
  una sola foto que pide HU36 cuando la otra no pasa el control de calidad.
- Se arma desde un modelo de una foto ya entrenado (backbone y cabeza), así que al empezar
  f(A, A) es exactamente el modelo de una foto.
- Solo usa capas estándar de Keras, para exportarlo a `.tflite` sin capas propias.
"""

from __future__ import annotations

from typing import Any

import keras

from melanoma.models.single_view import backbone

VIEWS = ("view_a", "view_b")


def build_two_view(single: keras.Model, fusion_cfg: dict[str, Any]) -> keras.Model:
    """Modelo de dos entradas (`view_a`, `view_b`) que comparte el backbone de `single`.

    Ojo: el backbone es el mismo objeto que en `single`; si se entrena este modelo, cambia
    también `single`. Hay que predecir con `single` antes.
    """
    L = keras.layers
    base = backbone(single)
    size = base.input_shape[1]
    inputs = {name: keras.Input((size, size, 3), name=name) for name in VIEWS}
    features = [base(inputs[name], training=False) for name in VIEWS]
    dim = features[0].shape[-1]
    stacked = L.Concatenate(axis=1, name="views")([L.Reshape((1, dim))(f) for f in features])
    score = L.Dense(fusion_cfg.get("hidden", 128), activation="tanh", name="view_score_hidden")(stacked)
    score = L.Dense(1, name="view_score")(score)                    # (lote, 2, 1)
    weights = L.Softmax(axis=1, name="view_weights")(score)
    fused = L.Reshape((dim,))(L.Dot(axes=1, name="fusion")([weights, stacked]))
    x = L.Dropout(fusion_cfg.get("dropout", 0.0), name="dropout")(fused)
    output = L.Dense(1, activation="sigmoid", dtype="float32", name="melanoma")(x)
    model = keras.Model(inputs, output, name="two_view_fusion")
    model.get_layer("melanoma").set_weights(single.get_layer("melanoma").get_weights())
    return model


def with_metadata(two_view: keras.Model, n_features: int, hidden: int = 32) -> keras.Model:
    """Agrega los datos del paciente (EXP-07): logit = logit de las fotos + logit de los datos.

    La rama de los datos es una red chica que termina en ceros, así que al empezar el modelo da
    exactamente lo mismo que `two_view`. Entradas: `view_a`, `view_b` y `metadata`.
    """
    L = keras.layers
    head = two_view.get_layer("melanoma")
    image_logit = L.Dense(1, dtype="float32", name="image_logit")(two_view.get_layer("dropout").output)
    metadata = keras.Input((n_features,), name="metadata")
    hidden_layer = L.Dense(hidden, activation="relu", name="metadata_hidden")(metadata)
    metadata_logit = L.Dense(1, kernel_initializer="zeros", bias_initializer="zeros",
                             dtype="float32", name="metadata_logit")(hidden_layer)
    logit = L.Add(dtype="float32", name="logit")([image_logit, metadata_logit])
    output = L.Activation("sigmoid", dtype="float32", name="melanoma")(logit)
    model = keras.Model({**two_view.input, "metadata": metadata}, output, name="two_view_metadata")
    model.get_layer("image_logit").set_weights(head.get_weights())
    return model


def view_weights(model: keras.Model) -> keras.Model:
    """Modelo auxiliar que devuelve el peso que la fusión le da a cada foto, (lote, 2)."""
    weights = keras.layers.Reshape((2,))(model.get_layer("view_weights").output)
    return keras.Model(model.inputs, weights)
