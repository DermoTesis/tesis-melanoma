# Pendientes: alineación de la app con el modelo y el paper

Revisión del 2026-11-13. Se cruzó la app con los experimentos del modelo (`../experiments`,
`../resultados`) y con el short paper v2 (versión comentada, con el alcance acotado a fotos
dermatoscópicas). Las rutas de este documento son relativas a la carpeta `app/`.

Leyenda: **D** = decisión del equipo, **A** = cambio en la app, **T** = cambio en los documentos
de la tesis o en el paper. Varias tareas dependen de una decisión previa; se indica en cada una.

## Resuelto

- [x] **La app decidía la alerta con la regla equivocada.** Comparaba la probabilidad
  calibrada con 0.070, pero el registro de EXP-04 decide con la salida sin calibrar
  (≥ 0.0138). Como la calibración isotónica tiene un escalón que cruza el umbral, sobre las
  1,662 lesiones de validación la app dejaba sin alerta 78 lesiones que el modelo marca,
  2 de ellas melanomas. Ahora `ModelArtifact` lleva los parámetros del registro y la clase
  sale de la salida sin calibrar
  ([mock_inference_engine.dart](lib/data/mock/mock_inference_engine.dart)). La prueba está
  en [mock_inference_engine_test.dart](test/data/mock_inference_engine_test.dart).

## Decisiones pendientes

- [ ] **D1. Qué es la segunda foto dermatoscópica.** El paper dice que las dos fotos son
  dermatoscópicas y que el modelo no distingue cuál es cuál (es simétrico y se entrenó con
  pares al azar), pero no da un protocolo de captura. La app tiene que darle al médico una
  instrucción concreta (por ejemplo, dos tomas con distinto aumento, o volver a apoyar el
  dermatoscopio entre una y otra). Si el médico toma dos fotos casi iguales, la ventaja de
  dos fotos sobre una puede desaparecer; ver el comentario DCA12 del paper sobre la
  similitud de los pares. **Instrucción provisional en la app (A1):** la foto 2 es la misma
  lesión, retirando el dermatoscopio y volviendo a apoyarlo con otro ángulo o posición.
  Falta que el equipo la confirme.
- [ ] **D2. Si se guarda una foto clínica de contexto.** Sería una foto sin dermatoscopio
  (la antigua panorámica), solo para el expediente y el informe, sin mandarla al modelo. Desde
  A1 la app ya no la captura y el informe PDF muestra las dos fotos dermatoscópicas. El paper
  no dice nada.
- [ ] **D3. El control de calidad de imagen y la H3.** La app rechaza fotos borrosas u
  oscuras antes de enviarlas (`ImageQualityService`). El paper no lo muestra en la Fig. 2,
  lo deja como trabajo futuro (VII-v) y dice en VI-A que, si la app rechaza las fotos
  malas, la ventaja de la fusión (sensibilidad estable con una foto degradada) pierde
  relevancia. Hay que decidir si el paper describe el control actual o si cambia el control
  de la app. El comentario DCA14 del paper apunta a lo mismo.

## Cambios en la app

- [x] **A1. Cambiar la captura a dos tomas dermatoscópicas** (2026-11-19). Los pasos ahora
  son "1 · Foto 1 / 2 · Foto 2" de la misma lesión, las dos con el marco circular
  ([capture_widgets.dart](lib/features/capture/capture_widgets.dart)). La guía de la foto 2
  pide retirar el dermatoscopio y volver a apoyarlo con otro ángulo (instrucción provisional
  de D1). `ImageView` pasó a `{foto1, foto2}`
  ([clinical_case.dart](lib/domain/models/clinical_case.dart)), igual en el informe, la
  galería, los casos de ejemplo y las pruebas
  ([capture_widgets_test.dart](test/features/capture_widgets_test.dart)). La app no
  comprueba que las dos fotos sean distintas; si D1 lo pide, falta ese control.
- [x] **A2. Quitar la opción "Sin dermatoscopio"** (2026-11-19). El paper deja fuera del
  alcance las fotos sin dermatoscopio. Se quitó el interruptor de la cámara
  ([camera_capture_screen.dart](lib/features/capture/camera_capture_screen.dart)) y el campo
  `conDermatoscopio` de `CaseImage` y `CaseDraft`, que ya no distinguía nada: toda foto del
  caso es dermatoscópica. El detalle del caso solo muestra si la foto vino de la cámara o
  de la galería.
- [ ] **A3. Recortar la foto antes de mandarla al modelo.** El modelo estira la imagen
  entera a 224×224 sin recortar, y se entrenó con imágenes 4:3 (600×450) que solo muestran
  el campo del dermatoscopio. La cámara de la app usa `ResolutionPreset.veryHigh`, que en
  Android da 1920×1080 (16:9), y con el dermatoscopio de clip la foto trae el campo
  circular al centro y bordes negros. Hay que definir, en la app o en el backend, un
  recorte al campo del dermatoscopio en 4:3. Las fotos de galería pueden venir en
  cualquier proporción.
- [ ] **A4. Revisar el texto "Unas X de cada 100 lesiones con este resultado son
  melanoma"** ([prediction.dart](lib/domain/models/prediction.dart), `frequencyText`).
  Esa cifra viene de una calibración hecha sobre lesiones de HAM10000 con 2 o más fotos,
  donde el 19.7% son melanomas; en una consulta real la proporción será otra. El propio
  paper (V-C) muestra que el valor predictivo positivo baja de 26% a 7% si la prevalencia
  pasa de 19.7% a 5%, y pide presentar la herramienta como apoyo al triaje (VI-C).
  Además, la calibración llega a 1.0, así que la app podría mostrar "100 de cada 100":
  como mínimo, poner un tope a lo que se muestra. El test todavía no se evalúa, así que la
  calibración tampoco está confirmada.
- [ ] **A5. Mostrar sin ambigüedad el escalón del 7%.** Toda salida entre 0.0040 y 0.0193
  se calibra a 0.0699. Por eso la tarjeta puede mostrar "Posible melanoma · riesgo 7%" en
  un caso y "Sin alerta · riesgo 7%" en otro, ambos con "Alerta desde 7%". La decisión ya
  es correcta; falta definir cómo presentar esa zona.
- [ ] **A6. Hacer que los casos simulados se parezcan a los reales.** El simulador reparte
  los casos así: 25% sin alerta, 15% bajo, 30% intermedio y 30% alto. Con las predicciones
  de validación del modelo real, el reparto es este:

  | Banda | Simulador | Validación | Melanomas en la banda |
  |---|---|---|---|
  | Sin alerta | 25% | 35% | 5% |
  | Baja (0.07–0.30) | 15% | 40% | 13% |
  | Intermedia (0.30–0.70) | 30% | 18% | 44% |
  | Alta (≥ 0.70) | 30% | 6% | 79% |

  Si la app se prueba con médicos, el simulador debería reflejar que la mayoría de las
  alertas son de riesgo bajo, consecuencia de exigir sensibilidad ≥ 90% (especificidad
  36%).
- [ ] **A7. Justificar los cortes 0.30 y 0.70 de las bandas.** No salen de ningún
  experimento. La tabla de A6 los respalda razonablemente, pero hay que dejarlo escrito en
  la memoria.
- [x] **A8. Mostrar la versión del modelo que devuelve el backend.** Resuelto: la app
  muestra `version_modelo` del backend y el simulado usa `20261004T172732Z_registro`. La app muestra
  `mnv3l-fusion-2v-fp16 v1`; el artefacto registrado es `20261004T172732Z_registro`, con
  su sha256 en `../resultados/exp04/20261004T172732Z_registro/registro.json`.
- [ ] **A9. Fijar el contrato del backend real.** La respuesta de inferencia debe traer la
  clase ya decidida (`clasePredicha`), la probabilidad calibrada y la versión del
  artefacto. La app no debe recalcular la clase (ver la regla en
  [dermavia-reglas-clinicas](.agents/skills/dermavia-reglas-clinicas/SKILL.md)).
- [ ] **A10. (Opcional) Avisar en las ubicaciones acrales.** El paper subraya que en Perú
  predomina el melanoma acral y que HAM10000 casi no tiene imágenes de palmas, plantas o
  uñas. La app ofrece "Planta del pie" y "Mano" como ubicaciones; podría mostrar un aviso
  de que el resultado es menos confiable en esas zonas.

## Documentos de la tesis y paper

- [ ] **T1. Alinear el alcance de la captura en la tesis.** El acta de constitución (ACP v3,
  p. 7) y la HU08 de la memoria v4 dicen "con o sin dermatoscopio"; el paper ahora exige
  dermatoscopio de clip. El RF-02.1 no menciona la panorámica, así que no cambia; sí
  cambian las pantallas 10–11 del mockup, que todavía muestran la panorámica (A1) y el
  interruptor "Con dermatoscopio / Sin" (A2).
- [ ] **T2. Paper III-B: decir que el backend también devuelve la clase.** Hoy dice que
  "returns the calibrated probability". La clase se decide con la salida sin calibrar,
  como muestra la Fig. 1.
- [ ] **T3. Paper III-A: el respaldo de una sola foto.** "If only one valid photograph is
  available, it is fed to both inputs", pero la app siempre exige las dos fotos, así que
  ese respaldo nunca se usa desde la app. Aclararlo o quitarlo (relacionado con DCA14).
- [ ] **T4. Paper Fig. 2 y III-B: el control de calidad** (depende de D3).
- [ ] **T5. Paper III-B: el estado de la app.** La frase PENDING sobre si la app está
  implementada y el comentario DCA17: hoy existe un prototipo con backend e inferencia
  simulados, sin backend en Cloud Run ni reglas de Firestore.
