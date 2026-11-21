---
name: dermavia-reglas-clinicas
description: Reglas de negocio clínicas de Dermavía que ningún cambio puede romper (consentimiento, estados del caso, validación inmutable, cierre solo tras validación, lenguaje de la predicción). Úsala antes de tocar lib/domain, lib/data/mock, los repositorios o cualquier pantalla que muestre casos, predicciones, validaciones o informes.
---

# Reglas clínicas de Dermavía

Dermavía es una herramienta de **apoyo diagnóstico** para melanoma maligno de uso
exclusivo del médico especialista. La app **no clasifica**: la inferencia ocurre en el
backend y su resultado es siempre una predicción preliminar que requiere validación
médica. Estas reglas se aplican en la capa de datos (`lib/data/mock/`), igual que en el
backend real, para que la UI no pueda saltárselas.

## 1. Flujo obligatorio del caso

```
REGISTRADO → EN_ANALISIS → (ERROR_ANALISIS) → PENDIENTE_VALIDACION → VALIDADO → CERRADO
```

- Enum: `CaseStatus` en [clinical_case.dart](../../../lib/domain/models/clinical_case.dart);
  `.code` da el código en mayúsculas y `.label` el texto para la UI.
- Solo `MockBackend.startAnalysis` / `_completeAnalysis` mueven un caso a
  `enAnalisis` / `pendienteValidacion` / `errorAnalisis`.
- `ERROR_ANALISIS` se reprocesa en `runScheduledTasks()` (simula Cloud Scheduler, cada
  20 s). `CASO-0197` falla a propósito en su primer análisis.
- Sin conexión, `submitCase` deja el caso en `REGISTRADO` con `queuedOffline: true`;
  `flushOfflineQueue()` lo envía al recuperar conexión (RF-02.4, RNF-08).
- **Nunca** añadas un atajo que salte estados (p. ej. `registrado → validado`).

## 2. Barreras que no se negocian

| Regla | Dónde se aplica | Excepción |
|---|---|---|
| Sin consentimiento vigente no hay captura ni caso (RF-02.6) | `submitCase` | `ConsentRequiredException` |
| El caso exige dos fotos dermatoscópicas aptas de la misma lesión (RF-02.1) | `submitCase` | `AppException` |
| Validar requiere predicción y **sustento clínico** no vacío (RF-04.2/04.3) | `registerValidation` | `AppException` |
| Corregir exige una clase distinta a la predicha | `registerValidation` | `AppException` |
| Validaciones **solo de inserción**: una segunda validación es complementaria (`complementaDe`), nunca una edición | `registerValidation` | `AppException` |
| Sin validación no hay cierre ni informe (RF-07.1) | `closeCase`, `buildReportDocument` | `ValidationRequiredException` |
| Las observaciones internas no salen en el informe exportable (RF-06.3, RF-05.5) | `ReportDocument` | — |
| La sugerencia de exámenes solo se edita en `PENDIENTE_VALIDACION` | `updateSuggestion` | `AppException` |
| Los casos son privados de quien los registró: otro médico no los ve ni los valida, anota o cierra (los pacientes y los informes cerrados sí se comparten) | `_b.ownCase` en lecturas y escrituras de casos | "Caso no encontrado." |

Toda operación clínica empieza con `_b.requireClinician()` (especialista activo, con
acceso clínico y alcance aceptado); las de administración con `_b.requireAdmin()`.

## 3. Errores para el médico (RNF-16)

- Lanza subclases de `AppException` ([app_exception.dart](../../../lib/core/errors/app_exception.dart))
  con un mensaje en español, en segunda persona, apto para mostrarse tal cual.
- El error de login es **genérico** (`AuthException`): nunca indiques si falló el correo
  o la contraseña (HU04·CA2). La recuperación de contraseña responde igual exista o no
  el correo.

## 4. Auditoría (RNF-17)

Cada acción relevante llama a `_b.log(AuditType.x, referencia)` antes de `_b.notify()`.
Si creas una acción nueva auditable, añade el valor a `AuditType` y su `label` en
[audit_event.dart](../../../lib/domain/models/audit_event.dart).

## 5. Lenguaje de la predicción (sin jerga de ML)

La tarjeta de predicción la lee un médico, no un científico de datos. En textos visibles:

- Usa **"riesgo estimado"**, **"línea de alerta"**, **"Posible melanoma"** /
  **"Sin alerta de melanoma"** y frecuencias naturales ("Unas 9 de cada 100…").
- **No** uses "probabilidad calibrada", "umbral", "modelo", "clasificador", "float16",
  "isotónica" ni "confianza del modelo" en la UI. Esos términos solo viven en código y
  comentarios.
- Reutiliza los getters de `Prediction` ([prediction.dart](../../../lib/domain/models/prediction.dart)):
  `headline`, `frequencyText`, `shortSummary`, `riskLabel`, `percent`, `alertPercent`,
  `defaultSuggestion`. No reconstruyas esos textos en las pantallas.
- Bandas de confianza (RF-06.1): `benigna` (sin alerta), `baja` (< 0.30),
  `ambigua` (0.30–0.70), `alta` (≥ 0.70).
- La clase (`clasePredicha`) la decide el backend con la salida **sin calibrar** del
  modelo (`ModelArtifact.decisionThreshold = 0.0138`). **Nunca** la deduzcas comparando
  la probabilidad calibrada con la línea de alerta (`ModelArtifact.calibratedThreshold`
  ≈ 0.070, solo para mostrar): la calibración tiene un escalón que cruza el umbral y el
  mismo 7% puede tener o no alerta.
- Toda predicción se presenta como preliminar; la decisión es siempre del especialista.

`test/features/prediction_card_test.dart` comprueba que "calibrada" y "umbral" no
aparezcan; mantenlo en verde.

## Checklist antes de terminar

- [ ] Ninguna transición de estado nueva salta la validación médica.
- [ ] Las reglas nuevas están en la capa de datos, no solo en la UI.
- [ ] Mensajes de error en español, genéricos donde corresponde.
- [ ] Evento de auditoría para la acción nueva.
- [ ] Ningún término de ML en textos visibles.
- [ ] Hay prueba en `test/data/mock_repositories_test.dart` para la regla.
