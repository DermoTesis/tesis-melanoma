# Pendientes: alineación de la app con el modelo y el paper

Revisión del 2026-11-21 (la anterior es del 2026-11-13). Se cruzó la app y el backend
desplegado con:

- los experimentos, ya completos: EXP-01 a EXP-11 y la evaluación única del test
  (`../resultados/exp04/20261114T005335Z_evaluacion-test`);
- la versión final del short paper
  ([Short Paper Final.docx](<../Documentos actualizados/Short Paper Final.docx>)), que ya no
  tiene comentarios abiertos;
- la memoria v10 ([formato_Tesis__memoria__v10.docx](<../Documentos actualizados/formato_Tesis__memoria__v10.docx>)).

Las rutas de este documento son relativas a la carpeta `app/`. Las secciones del paper
(III-A, V-C…) son las de la versión final.

Leyenda: **D** = decisión del equipo, **A** = cambio en la app (o en el backend, si se
indica), **T** = cambio en los documentos de la tesis. Los ids se conservan entre revisiones
porque el backend y otros documentos los citan (A3, A7, D1).

**Prioridad de esta revisión:** la sección "Cómo se presenta el resultado al médico". Las
cifras del test que se citan salen de `predicciones_test.csv` (294 lesiones con dos o más
fotos, 57 melanomas). Los cambios de esa sección que no dependían de una decisión se aplicaron
el mismo 2026-11-21. Quedan abiertos A15 (necesita un dermatólogo) y A7 (memoria).

## Resuelto

- [x] **La app decidía la alerta con la regla equivocada** (2026-11-13). Ahora la clase sale
  de la salida sin calibrar (≥ 0.0138), como en el registro de EXP-04
  ([mock_inference_engine.dart](lib/data/mock/mock_inference_engine.dart), prueba en
  [mock_inference_engine_test.dart](test/data/mock_inference_engine_test.dart)).
- [x] **A1. Captura de dos tomas dermatoscópicas** (2026-11-19). Pasos "1 · Foto 1 /
  2 · Foto 2" con marco circular
  ([capture_widgets.dart](lib/features/capture/capture_widgets.dart)); `ImageView` es
  `{foto1, foto2}` y el backend usa vistas `a` y `b`. El protocolo de la segunda foto quedó
  fijado en D1.
- [x] **A2. Quitar la opción "Sin dermatoscopio"** (2026-11-19). Coincide con el paper
  (VI-D: las fotos sin dermatoscopio quedan fuera del alcance).
- [x] **A8. Versión del modelo.** La app muestra `version_modelo` del backend; el simulado usa
  `20261004T172732Z_registro`.
- [x] **A9. Contrato del backend.** `PrediccionOut` trae `clase_predicha`,
  `probabilidad_malignidad`, `linea_alerta`, `banda` y `version_modelo`; la app los lee en
  [codecs.dart](lib/data/remote/codecs.dart) y no recalcula la clase (I2 de
  [INTEGRACION_BACKEND.md](INTEGRACION_BACKEND.md)).
- [x] **T2. Paper III-B: el backend devuelve la clase.** La versión final dice que el
  servicio "would return a preliminary class from the registered raw-score threshold and a
  calibrated probability".
- [x] **T3. Paper III-A: el respaldo de una sola foto.** La versión final aclara que solo se
  usa en la población secundaria del test y que "the intended application always requires two
  photographs".
- [x] **T4. Paper: el control de calidad.** La Fig. 2 no lo muestra y el texto lo trata como
  trabajo futuro sin evaluar (V-B: "We did not evaluate a quality detector"; VII-v). Lo que
  queda pendiente está del lado de la app y de la memoria (D3).
- [x] **T5. Paper III-B: el estado de la app.** La versión final describe el prototipo con
  los commits 19d94f8, 24e46c5 y c47d529 y deja Cloud Run como "planned". El paper está
  cerrado: el despliegue real (2026-11-21) se refleja en la memoria (T13).
- [x] **D1. Qué es la segunda foto dermatoscópica** (decidido el 2026-11-21). Se mantiene la
  instrucción de la app: la foto 2 es la misma lesión, tomada después de retirar el
  dermatoscopio y volver a apoyarlo con otro ángulo o posición. La app **no** rechaza dos fotos
  casi idénticas. El paper no fija un protocolo (el modelo es simétrico, III-A) y reconoce
  que no se midió cuánto se parecen las fotos de cada par (VI-D, "Pair similarity"). La
  instrucción se documenta en la memoria (T1).
- [x] **D2. Foto clínica de contexto** (decidido el 2026-11-21). No se guarda: el caso tiene
  solo las dos fotos dermatoscópicas que van al modelo, y son las que muestra el informe PDF.
  Así funciona la app desde A1, así que no requiere cambios.
- [x] **D4. Impresión clínica antes de ver el resultado** (decidido e implementado el
  2026-11-21). El paper cita que un consejo erróneo de la IA empeoró las decisiones de los
  médicos en experimentos de lectura (VI-C, ref. [37]). Se eligió pedir la impresión **antes de
  ver el resultado**, y se implementó al registrar el caso: en "Datos de la lesión" el médico
  elige "Sospecho melanoma", "No sospecho melanoma" o "Dudosa" antes de enviar a análisis. Así
  la registra antes de que exista una predicción y no hay que ocultar resultados en el panel,
  las alertas ni el historial. Es parte de `ClinicalData` (`impresionClinica` en la app,
  `impresion_clinica` en el backend), no se puede cambiar después y se muestra en el detalle
  ("Tu impresión") y en la validación ("Tu impresión previa"). La exigen `submitCase` (simulado
  y REST) y `POST /cases` (422 sin ella). El evento de auditoría de la validación la incluye,
  así que el monitoreo (T15) puede medir si el médico cambia de opinión al ver el resultado.
  Los casos registrados antes muestran "No registrada".
- [x] **D5. Constancia del uso de la herramienta en el informe** (decidido e implementado el
  2026-11-21). El PDF dice: "Caso evaluado con apoyo de Dermavía (versión X), herramienta de
  apoyo diagnóstico para melanoma. Su predicción preliminar fue revisada por el especialista, a
  quien corresponde la conclusión." Sigue sin incluir la predicción (RF-05.5). El backend la
  envía en `constancia_herramienta` del documento del informe (`informes.constancia_herramienta`)
  y la app la arma con `toolUsageNotice` en el modo simulado. Si un backend anterior no la
  envía, la app usa el mismo texto sin la versión.
- [x] **D6. Quitar la región subungueal** (decidido e implementado el 2026-11-21). HAM10000
  excluyó esas lesiones (IV-A), así que "Región subungueal" salió de la lista de ubicaciones
  (`kBodySites`). Si se escribe en "Otra ubicación" (por ejemplo, "uña"), se mantiene el aviso
  de A10.

## Decisiones pendientes

- [ ] **D3. Qué hacer con el control de calidad actual.** La app rechaza fotos borrosas u
  oscuras con heurísticas (`ImageQualityService`: lado mínimo de 1024 px, luminancia entre 55
  y 228, varianza del Laplaciano ≥ 18) cuyos cortes no se contrastaron con el modelo. El paper
  lo deja sin evaluar, y la memoria v10 dice que será un modelo con `tflite_flutter` (T10). El
  test muestra que importa: con una foto degradada, la fusión bajó a 86.0–87.7% de
  sensibilidad, por debajo del 90% (V-D). Opciones: mantener las heurísticas y describirlas en
  la memoria como no validadas, o calibrar los cortes con las degradaciones de EXP-10.
## Cómo se presenta el resultado al médico

Revisión de la tarjeta de predicción
([case_detail_screen.dart](lib/features/case_review/case_detail_screen.dart),
`PredictionCard`), los textos de [prediction.dart](lib/domain/models/prediction.dart), el
panel, el historial, las alertas, la validación y el informe.

Resumen del test (población principal) para dimensionar cada punto:

| Banda | Lesiones | Melanomas en la banda | Riesgo medio mostrado |
|---|---|---|---|
| Sin alerta | 113 (38.4%) | 5 (4.4%) | 4.8% |
| Baja (0.07–0.30) | 131 (44.6%) | 24 (18.3%) | 12.0% |
| Intermedia (0.30–0.70) | 41 (13.9%) | 20 (48.8%) | 42.6% |
| Alta (≥ 0.70) | 9 (3.1%) | 8 (88.9%) | 79.4% |

De cada 10 alertas, unas 7 fueron lesiones no melanoma (129 de 181). Quedaron sin alerta 5 de
57 melanomas (1 de cada 11) y 13 de 23 carcinomas basocelulares.

- [x] **A11. "Riesgo muy bajo" en todo caso sin alerta** (hecho, 2026-11-21). En el test, el
  4.4% de los casos sin alerta fueron melanomas y más de la mitad de los carcinomas
  basocelulares cayó ahí. Ahora la banda se rotula "Por debajo de la línea de alerta", sin
  calificativo de riesgo (`riskLevel` es nulo), y el enum pasó de `benigna` a
  `PredictionConfidence.sinAlerta`, igual que el backend (`sin_alerta`).
- [x] **A12. El resultado no decía que solo evalúa melanoma** (hecho, 2026-11-21). El paper
  advierte que "a non-melanoma output for a basal cell carcinoma could falsely reassure the
  user" (V-C). La tarjeta muestra siempre `Prediction.scopeText` ("Solo evalúa melanoma: no
  descarta otros cánceres de piel, como el carcinoma basocelular"), y "¿Cómo leer este
  resultado?" tiene una sección "Qué no evalúa". La aceptación del alcance
  ([scope_acceptance_screen.dart](lib/features/auth/scope_acceptance_screen.dart)) agrega un
  punto con los límites del paper (VI-D, VII): solo fotos dermatoscópicas, desarrollado con
  dermatoscopias de Austria y Australia, sin validar con dermatoscopio de clip ni en
  pacientes peruanos.
- [x] **A4. La frase "Unas X de cada 100 lesiones con este resultado son melanoma"** (hecho,
  2026-11-21). La cifra viene de una calibración con 19.7% de melanomas, y el paper muestra
  que el valor predictivo positivo baja de 26.3% a 4.3% con 3% de prevalencia (V-C). Ahora
  `frequencyText` dice "En las lesiones con las que se desarrolló el sistema, unas X de cada
  100…", solo aparece con alerta, y "¿Cómo leer…?" explica que en esas lesiones 1 de cada 5
  era melanoma y que en la consulta la proporción probablemente será menor. **Sigue abierto:**
  la calibración no se evaluó en el test (allí el escalón del 18% tuvo 15 melanomas en 41
  lesiones, 37%). Si se evalúa, puede cambiar la cifra que se muestra.
- [x] **A5. Los escalones de la calibración, en especial el 7%** (hecho, 2026-11-21). En el
  test, 74 de 294 casos (25%) caen en el 7%: 15 con alerta y 59 sin alerta. Sin alerta ya no
  se muestra el porcentaje (ni en la tarjeta, ni en `shortSummary`, ni en el panel), así que
  el mismo 7% ya no aparece con dos lecturas. El riesgo se muestra con `riskText`, con piso
  "< 3%" y techo "> 90%". No hizo falta el rótulo "en la línea de alerta" para las alertas del
  escalón: su 7% ya no compite con un "Sin alerta · 7%".
- [x] **A13. "¿Cómo leer este resultado?" usaba términos vagos** (hecho, 2026-11-21). Ahora
  usa las cifras del test, con la aclaración de que salen de las pruebas del sistema: "detectó
  52 de 57 melanomas", "unas 7 de cada 10 alertas no fueron melanoma" y, sin alerta, "1 de
  cada 11 melanomas quedó por debajo de la línea de alerta". Las cifras viven en
  `ReferencePerformance` ([prediction.dart](lib/domain/models/prediction.dart)).
- [x] **A14. El orden del panel podía poner un caso sin alerta por encima de uno con alerta**
  (hecho, 2026-11-21). `_byProbability` ([case_providers.dart](lib/providers/case_providers.dart))
  ordena primero por `isAlert` y después por probabilidad. La prueba está en
  [mock_repositories_test.dart](test/data/mock_repositories_test.dart). Falta reflejarlo en
  RF-06.2 de la memoria, que habla de "probabilidad preliminar de malignidad".
- [ ] **A15. Revisar las sugerencias de exámenes con un dermatólogo** (RF-06.1;
  [sugerencias.py](../backend/dermavia/dominio/sugerencias.py) y `defaultSuggestion`, que
  tienen los mismos textos). No se cambió porque es contenido clínico. Tres problemas:
  - la banda intermedia sugiere estudios "para descartar un falso positivo antes de concluir",
    pero ahí la mitad de los casos del test fueron melanomas (48.8%): el texto empuja a leer el
    caso como benigno;
  - la banda baja propone "control dermatoscópico en 3 meses" para una lesión con alerta. Es una
    conducta concreta que ningún experimento respalda;
  - la banda alta no lleva sugerencia.

  Además, RF-06.1 habla de "confianza baja o ambigua", y la app lo implementa como riesgo bajo
  o intermedio: no es lo mismo. Hay que definir qué significa y dejarlo escrito (va con A7).
- [x] **A6. Casos simulados parecidos a los reales** (hecho, 2026-11-21). El simulador
  (`MockInferenceEngine.predict`) reparte ahora como la validación: 35% sin alerta, 40% baja,
  18% intermedia y 7% alta. Los casos sembrados de `seed_data.dart` tienen salidas fijas y no
  cambian.

  | Banda | Simulador antes | Simulador ahora | Validación | Test |
  |---|---|---|---|---|
  | Sin alerta | 25% | 35% | 35% | 38% |
  | Baja (0.07–0.30) | 15% | 40% | 40% | 45% |
  | Intermedia (0.30–0.70) | 30% | 18% | 18% | 14% |
  | Alta (≥ 0.70) | 30% | 7% | 6% | 3% |

- [ ] **A7. Justificar los cortes 0.30 y 0.70 de las bandas.** No salen de ningún experimento.
  Separan bandas con 13%, 44% y 79% de melanomas en validación, y 18%, 49% y 89% en el test.
  Dejarlo escrito en la memoria. La banda alta tiene solo 9 casos en el test.
- [x] **A16. La palabra "Modelo" en textos visibles** (hecho, 2026-11-21). El panel muestra
  "Preliminar: …" en los casos validados; la validación registrada, "Predicción"; "¿Cómo
  leer…?", "Versión …"; y el perfil, "Versión de análisis". La prueba de la tarjeta comprueba
  que "Modelo" no aparezca.

## Otros cambios en la app y el backend

- [x] **A17. Redesplegar el backend por D4 y D5** (hecho, 2026-11-21). Imagen `20261121-d4d5`,
  revisión `dermavia-api-00002-pzr`. `/health` responde y el contrato publicado exige
  `impresion_clinica` y devuelve `constancia_herramienta`. **Falta:** reinstalar la app en los
  celulares de prueba, porque las instalaciones anteriores no envían la impresión y el servicio
  las rechaza (422), y repetir la prueba de extremo a extremo (N13 de
  [CONEXION_NUBE.md](CONEXION_NUBE.md)) con un caso nuevo.
- [ ] **A3. Recortar la foto al campo del dermatoscopio antes del modelo.** El modelo estira
  la imagen entera a 224×224 sin recortar (IV-C) y se entrenó con imágenes 4:3 (600×450). La
  cámara usa `ResolutionPreset.veryHigh` (1920×1080 en Android), y con el dermatoscopio de clip
  la foto trae el campo circular al centro y bordes negros. `melanoma.serving.preprocess`
  todavía redimensiona la foto entera. Falta decidir si el recorte a 4:3 va en la app o en el
  backend ([backend/README.md](../backend/README.md), "Pendiente"). Las fotos de galería
  pueden venir en cualquier proporción.
- [x] **A10. Ubicaciones fuera del dominio del modelo.** HAM10000 excluyó las lesiones
  subungueales, mucosas y oculares (IV-A). Además, solo 7 de sus imágenes tienen la etiqueta
  "acral", todas de nevus (I, VI-D), y en el Perú el melanoma acral es frecuente (38.1% en la
  serie del INEN). **Hecho (2026-11-21):** `siteNoticeFor`
  ([clinical_case.dart](lib/domain/models/clinical_case.dart)) muestra un aviso en los datos
  clínicos al elegir la ubicación y en el detalle del caso, junto a la predicción: en mano o
  planta, que el resultado es menos confiable si la lesión está en la palma o la planta; en una
  lesión subungueal escrita en "Otra ubicación", que no tiene respaldo. La región subungueal ya
  no está en la lista (D6).

## Alineación de la app y el despliegue con los documentos

El paper está cerrado. Salvo T1, estos puntos son cambios en la memoria v10 o decisiones
para que el sistema coincida con lo que ella describe.

- [ ] **T1. El alcance de la captura en la memoria y el acta.** La memoria v10 todavía
  describe una foto panorámica y una de acercamiento, y en algunos lugares "con o sin
  dermatoscopio". Aparece en la sección 3.3 (pipeline y fusión "a dos escalas"), en RF-02.1,
  en el CU de captura, en la HU08, en el modelo de datos (`panoramica` / `acercamiento`; el
  backend usa `a` y `b`) y en los mockups de la Fig. 10. El acta de constitución (ACP v3,
  p. 7) también dice "con o sin dermatoscopio". Todo debe decir "dos fotos dermatoscópicas de
  la misma lesión con smartphone y dermatoscopio de clip", con la instrucción de captura de
  D1: retirar el dermatoscopio y volver a apoyarlo con otro ángulo o posición. Conviene
  aclarar que el sistema no comprueba que las dos fotos sean distintas, y que no se guarda una
  foto clínica sin dermatoscopio (D2).
- [ ] **T9. "Benigno/maligno" en RF-03.3 y en la memoria.** RF-03.3, la sección 3.3 y el CU de
  envío hablan de clasificación "benigno/maligno". El modelo, el backend, la app y el paper
  usan melanoma / no melanoma. Es el mismo problema de fondo que A12.
- [ ] **T10. El control de calidad y el almacenamiento local en la tabla de componentes.** La
  memoria lista `tflite_flutter (solo control de calidad)` y `flutter_secure_storage`. La app
  usa heurísticas (D3) y guarda la cola offline con `shared_preferences`. Actualizar la tabla o
  la app.
- [ ] **T11. Región de Cloud Scheduler.** La Tabla 5 de la memoria pone todos los nodos en
  Santiago, pero las tareas `dermavia-reprocesar` y `dermavia-alertas-vencidas` corren en
  `southamerica-east1` (São Paulo) según [backend/README.md](../backend/README.md). No llevan
  datos clínicos, pero la memoria afirma que todo está en Santiago: corregir la tabla o
  explicar la excepción.
- [ ] **T12. La base de validaciones "de solo inserción".** La memoria y el paper (III-B,
  "append-only rules") lo presentan como reglas de Firestore. En el despliegue, las reglas
  niegan todo acceso de clientes y la inserción única la garantiza el backend (solo usa
  `create`); IAM no permite un permiso de solo creación. Describirlo así en la memoria.
- [ ] **T13. Estado real del despliegue en la memoria.** Desde el 2026-11-21 el backend está
  en Cloud Run (`southamerica-west1`, proyecto `tesis-dermavia`) y la app lo usa en modo `nube`
  con Firebase Authentication y push ([CONEXION_NUBE.md](CONEXION_NUBE.md)). La memoria debe
  reflejarlo, junto con las diferencias de endpoints y esquema que lista el backend
  ([backend/README.md](../backend/README.md), "Diferencias con la memoria v10").
- [ ] **T14. Informe en PDF.** La Fig. 2 del paper y la memoria ponen el PDF en el backend
  ("Reports: case closure and PDF report"); hoy lo genera la app y `GET /reports/{id}/pdf` no
  existe. Implementarlo o describir que el PDF se genera en el dispositivo.
- [ ] **T15. Monitoreo del modelo en producción (RF-03.6, RNF-14).** El backend registra la
  concordancia médico–modelo por versión, pero falta el sink de Cloud Logging y la métrica
  basada en registros (paso 11 del despliegue en [backend/README.md](../backend/README.md)).
  Sin eso, RNF-14 no se cumple en el despliegue.
- [ ] **T16. Latencia en la nube (RNF-09).** El paper dice que "cloud latency remains
  unmeasured". Falta medir en Cloud Run el p95 por caso, cuatro casos simultáneos y el
  arranque en frío (con 0 instancias mínimas, C4 de CONEXION_NUBE.md).
- [ ] **T17. RNF-15: "umbral mínimo de precisión".** En la tabla, "precisión" se lee como el
  valor predictivo positivo, que en el test fue 28.7%. El criterio que realmente se fijó y se
  evaluó es la sensibilidad ≥ 90% (H1: 91.2% [82.7, 98.1]). Reformular RNF-15 con esa métrica.
- [ ] **T18. Las decisiones D4, D5 y D6 en la memoria.** Registrar la impresión clínica previa
  como requisito (junto a RF-02.3 o como uno nuevo), con su HU y su mockup en la Fig. 10;
  agregar la constancia de uso a RF-05.2/RF-05.3 y al mockup del informe (Fig. 11); quitar la
  región subungueal de las ubicaciones si la memoria las lista; y sumar `impresion_clinica` al
  modelo de datos de `casos`.
