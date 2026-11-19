# Integración de la app con el backend real

Revisión del 2026-11-19. Se cruzó la app (con el backend simulado de `lib/data/mock/`) con el
backend de [`../backend`](../backend/README.md) (FastAPI, monolito modular para Cloud Run) para
registrar todo lo que hay que cambiar en la app antes de conectarla. Las rutas de este
documento son relativas a la carpeta `app/`. El contrato de referencia del backend está en
[esquemas.py](../backend/dermavia/presentacion/esquemas.py) y
[rutas.py](../backend/dermavia/presentacion/rutas.py) (también en `/docs` del servidor).

**Estrategia acordada:**

- **Fase 1 · servidor local.** La app se conecta a `python -m dermavia.local` (todo en memoria,
  modelo real de EXP-04) con tokens de desarrollo `Authorization: Bearer dev:<uid>`.
- **Fase 2 · Firebase y Cloud Run.** Firebase Authentication, Cloud Messaging y la URL de Cloud
  Run, cuando exista el proyecto de Google Cloud (hoy pendiente, ver README del backend).
- El backend simulado **se conserva** para las pruebas y la demo sin red.

## Estado (2026-11-19)

La **fase 1 está implementada**: con `--dart-define=DERMAVIA_BACKEND=local` la app usa
la API REST del servidor local (`lib/data/remote/`); sin esa opción sigue usando el
backend simulado. Quedan para la fase 2 las partes de Firebase de I13, I15 e I16, las
notificaciones push (I22) y el modo `nube`. Las tareas marcadas `[x]` están hechas;
las notas **Fase 1** indican lo que quedó resuelto de forma provisional.

Archivos principales: [backend_config.dart](lib/data/remote/backend_config.dart),
[api_client.dart](lib/data/remote/api_client.dart),
[codecs.dart](lib/data/remote/codecs.dart),
[refresh_hub.dart](lib/data/remote/refresh_hub.dart),
[local_case_store.dart](lib/data/remote/local_case_store.dart),
[rest_repositories.dart](lib/data/remote/rest_repositories.dart),
[remote_connectivity.dart](lib/data/remote/remote_connectivity.dart),
[token_provider.dart](lib/data/remote/token_provider.dart) y el selector en
[repository_providers.dart](lib/providers/repository_providers.dart).

Leyenda: **I** = cambio en la app para la integración. Los ids **D**, **A** y **T** son los de
[PENDIENTES.md](PENDIENTES.md).

## 1. Arquitectura de la integración

- [x] **I0. Capa remota y selector de backend.**
  - La app **no puede leer Firestore**: las reglas niegan todo acceso de clientes
    ([firestore.rules](../backend/firestore.rules)); todo pasa por la API REST. Por eso los
    `Stream` de los repositorios se arman con **REST + refresco**: una petición al suscribirse,
    sondeo periódico mientras la pantalla está activa y recarga inmediata después de cada
    escritura. La UI no cambia, porque sigue consumiendo `Stream`s.
  - Crear `lib/data/remote/` con:
    - `ApiClient`: URL base, cabecera `Authorization: Bearer <token>`, JSON, tiempo de espera
      y mapeo de errores (I12).
    - `TokenProvider`: `DevTokenProvider` (fase 1) y `FirebaseTokenProvider` (fase 2).
    - DTOs con `fromJson`/`toJson` que traducen el JSON del backend a los modelos de
      `lib/domain/models/` (ver la sección 3).
    - Un `Rest*Repository` por contrato de
      [repositories.dart](lib/domain/repositories/repositories.dart).
  - En [repository_providers.dart](lib/providers/repository_providers.dart), elegir la
    implementación con `--dart-define=DERMAVIA_BACKEND=mock|local|nube` y
    `--dart-define=DERMAVIA_API_URL=...` (local en el emulador: `http://10.0.2.2:8080`).
    `mock` sigue siendo el valor por defecto para las pruebas.
  - `clockProvider` hoy sale de `mockBackendProvider`: en los modos remotos debe usar
    `DateTime.now` sin crear el `MockBackend`.
  - Dependencias nuevas en `pubspec.yaml`: `http` (cliente y `MockClient` para pruebas),
    `shared_preferences` o `path_provider` (cola offline y orden manual), `connectivity_plus`.
    Fase 2: `firebase_core`, `firebase_auth`, `firebase_messaging`.

## 2. Mapeo de repositorios a endpoints

| Método de la app | Endpoint del backend |
|---|---|
| `AuthRepository.signIn` / `authStateChanges` / `currentUser` | token (I13) + `GET /users/me` |
| `AuthRepository.acceptScope` | `POST /users/me/terms` |
| `AuthRepository.findActivation` / `getActivation` / `activateAccount` | sin equivalente: flujo de Firebase (I15) |
| `AuthRepository.requestPasswordReset` / `resetPassword` / `expireResetLink` | sin equivalente en el backend: Firebase (I16) |
| `AdminRepository.watchUsers` | `GET /admin/users` (filtrar especialistas en la app) |
| `AdminRepository.createSpecialist` | `POST /admin/specialists` |
| `AdminRepository.setClinicalAccess` | `PATCH /admin/users/{uid}/role` con `{"acceso_clinico": bool}` |
| `AuditRepository.watchEvents` | `GET /admin/audit?limite=200` |
| `PatientRepository.watchPatients` / `watchPatient` | `GET /patients` / `GET /patients/{id}` |
| `PatientRepository.findByHistoriaClinica` | `GET /patients?hc=` (lista vacía = no existe) |
| `PatientRepository.registerPatient` | `POST /patients` |
| `PatientRepository.registerConsent` / `revokeConsent` | `POST /patients/{id}/consent` / `DELETE /patients/{id}/consent` |
| `CaseRepository.watchMyCases` | `GET /cases` |
| `CaseRepository.watchCase` | `GET /cases/{id}` (sondeo liviano con `GET /cases/{id}/status`) |
| `CaseRepository.watchCasesForPatient` | `GET /patients/{id}/cases` |
| `CaseRepository.submitCase` | `POST /cases` → `POST /cases/{id}/upload-url` (vistas `a` y `b`) → `PUT` a cada URL firmada → `POST /cases/{id}/submit` |
| `CaseRepository.retryAnalysis` | `POST /cases/{id}/submit` (reanaliza si el caso está en `ERROR_ANALISIS`) |
| `CaseRepository.setManualOrder` / `manualOrder` | sin endpoint: guardar en el dispositivo (I20) |
| `CaseRepository.updateSuggestion` | `PUT /cases/{id}/suggestion` con `{"texto"}` |
| `CaseRepository.addInternalNote` | `POST /cases/{id}/notes` con `{"texto"}` |
| `ValidationRepository.watchValidations` | `GET /cases/{id}/validations` |
| `ValidationRepository.registerValidation` | `POST /validations` |
| `ReportRepository.closeCase` | `POST /cases/{id}/close` con `{"conducta_clinica"}` |
| `ReportRepository.buildReportDocument` | `GET /reports/{id}` (+ `GET /cases/{id}` para las fotos, I9) |
| `ReportRepository.watchReport` | `GET /reports/{id}`; `validation-required` = todavía no hay informe |

El backend tiene además `GET /cases/pending` (cola de validación ya ordenada),
`GET /patients/{id}/reports` (historial de informes cerrados) y `POST /users/me/devices` (FCM),
que la app puede usar en I6, I9 y I22.

## 3. Cambios de contrato en los modelos

- [x] **I1. Clase de lesión `melanoma` / `no_melanoma`.** La app usa
  `LesionClass { benigno, maligno }`
  ([prediction.dart](lib/domain/models/prediction.dart)); el backend usa `melanoma` /
  `no_melanoma`, porque el modelo distingue melanoma frente a todas las demás clases.
  Renombrar a `{ melanoma, noMelanoma }` con etiquetas "Melanoma" / "No melanoma" y revisar:
  - `Prediction.isAlert` y `ClinicalValidation.reportConclusion`
    ([validation.dart](lib/domain/models/validation.dart)), que debe decir "Lesión compatible
    con melanoma" / "Lesión no compatible con melanoma", igual que
    [informes.py](../backend/dermavia/dominio/informes.py);
  - el selector de clase al corregir
    ([validation_form_screen.dart](lib/features/validation/validation_form_screen.dart));
  - [case_widgets.dart](lib/features/dashboard/case_widgets.dart),
    [seed_data.dart](lib/data/mock/seed_data.dart),
    [mock_inference_engine.dart](lib/data/mock/mock_inference_engine.dart) y las pruebas.
- [x] **I2. Predicción.** `PrediccionOut` trae `probabilidad_malignidad`, `clase_predicha`,
  `linea_alerta`, `banda`, `version_modelo` y `fecha_inferencia`.
  - `Prediction.umbralOperativo` ← `linea_alerta` (solo para mostrar).
  - `Prediction.confidence` debe salir de `banda` (`sin_alerta`, `baja`, `ambigua`, `alta`)
    en vez de recalcular los cortes 0.30/0.70 en la app; el backend también entrega la
    sugerencia por defecto en `sugerencia_examenes`.
  - La clase sigue viniendo decidida del backend: la app nunca la recalcula (A9 resuelto en
    el backend).
  - Mostrar `version_modelo` real (`20261004T172732Z_registro`), lo que cierra A8.
- [x] **I3. Vistas de las fotos.** Desde A1, la app usa `ImageView { foto1, foto2 }`
  ([clinical_case.dart](lib/domain/models/clinical_case.dart)): dos fotos dermatoscópicas
  de la misma lesión. El cliente REST mapea `foto1` → `a` y `foto2` → `b`, las vistas
  neutras del backend. El modelo es simétrico, así que el orden no cambia el resultado.
- [x] **I4. `CaseImage`.** El backend no guarda `source`, así que pasa a ser opcional
  (`conDermatoscopio` se quitó con A2: toda foto del caso es dermatoscópica).
  - Agregar `remoteUrl`, que viene de `urls_imagenes` de `GET /cases/{id}` (solo en el
    detalle, URL firmadas que **vencen en 15 min**: no guardarlas, pedirlas otra vez).
  - Conservar `localPath` para los casos capturados en este dispositivo.
  - `LesionThumbnail` ([common.dart](lib/core/widgets/common.dart)) debe mostrar también una
    imagen de red. En listas (`GET /cases` no trae URL) usar la foto local o un marcador.
  - Afecta a [case_detail_screen.dart](lib/features/case_review/case_detail_screen.dart),
    [case_widgets.dart](lib/features/dashboard/case_widgets.dart) y
    [patient_history_screen.dart](lib/features/patients/patient_history_screen.dart).
- [x] **I5. `ClinicalCase`.**
  - `CasoOut` no trae `uid_medico`: hacerlo opcional (el backend ya filtra por médico).
  - Agregar `ultimoError` (`ultimo_error`, mensaje apto para el médico), `alertaVencido`
    (`alerta_vencido`) y `vistasCargadas` (`vistas_cargadas`).
  - `analysisAttempts` ← `intentos_analisis`; `suggestion` ← `sugerencia_examenes`;
    `internalNotes` ← `notas_internas` (`texto`, `autor_nombre`, `fecha`).
  - Los ids del backend son hex de 20 caracteres, no `CASO-0201`. Definir un id visible
    corto en la UI (p. ej. los 8 primeros en mayúsculas) o pedir al backend un correlativo.
- [x] **I6. Casos vencidos (RF-04.5).** `overdueCasesProvider`
  ([case_providers.dart](lib/providers/case_providers.dart)) mide 48 h desde `createdAt`;
  el backend las mide desde `prediccion.fecha_inferencia` y marca `alerta_vencido`.
  Alinear la app con el backend.
- [x] **I7. Paciente y consentimiento.**
  - `ConsentimientoOut` no trae `uid_medico`: hacer opcional `Consent.uidMedico`
    ([patient.dart](lib/domain/models/patient.dart)). Usar `consentimiento_vigente` del
    backend.
  - Fechas: `fecha_nacimiento` llega como `YYYY-MM-DD`; los `datetime` llegan en UTC y se
    muestran con `toLocal()`.
  - La HC se normaliza en el backend quitando **todos** los espacios y pasando a mayúsculas;
    el mock solo hace `trim()`. Igualar el mock.
- [x] **I8. Validación.** `ValidacionOut` no trae `uid_especialista` (hacerlo opcional en
  `ClinicalValidation`). `cmp` ← `numero_colegiatura`, `caseId` ← `id_caso`,
  `prediccionOriginal` ← `prediccion_original` (mismo formato que I2). La clase final la
  completa el backend al confirmar; `clase_final` solo se manda al corregir.
- [x] **I9. Informe.**
  - `CaseReport` ← `InformeOut` (`id`, `id_caso`, `id_validacion`, `conducta_clinica`,
    `fecha_cierre`).
  - `ReportDocument` ([report.dart](lib/domain/models/report.dart)) ← `DocumentoInformeOut`,
    que trae además `decision`, `sustento_clinico`, `examenes_adicionales`,
    `fecha_nacimiento` e `id_informe`. Decidir si el PDF los muestra.
  - El backend no entrega las fotos con el informe. Para el PDF
    ([report_pdf.dart](lib/features/reports/report_pdf.dart)), tomar `urls_imagenes` de
    `GET /cases/{id}` y descargar las imágenes antes de generar el documento.
  - El texto de alcance viene en `alcance`; usar ese en vez de `kScopeNotice`.
- [x] **I10. Auditoría.** `AuditType`
  ([audit_event.dart](lib/domain/models/audit_event.dart)) frente a `TipoEvento` del backend:
  `cambioRol` ↔ `cambio_permisos`; faltan en la app `prediccion`, `errorAnalisis` y
  `alertaVencido`; `anonimizacion` todavía no existe en el backend (RF-07.3).
  `actorName` ← `actor_nombre`, `timestamp` ← `fecha`. Un tipo desconocido no debe romper
  la lista.
- [x] **I11. Valores JSON de los enums.**

  | Enum de la app | Valores del backend |
  |---|---|
  | `CaseStatus` | `REGISTRADO`, `EN_ANALISIS`, `ERROR_ANALISIS`, `PENDIENTE_VALIDACION`, `VALIDADO`, `CERRADO` (ya coinciden con `.code`) |
  | `Sex` | `femenino`, `masculino` |
  | `Phototype` | `I`, `II`, `III`, `IV`, `V`, `VI` (coincide con `.roman`) |
  | `OnsetTime` | `menos_3_meses`, `entre_3_y_12_meses`, `mas_de_1_anio`, `no_sabe` |
  | `Symptom` | `cambio_tamano`, `picor`, `sangrado`, `cambio_color`, `dolor` |
  | `ValidationDecision` | `confirmar`, `corregir`, `descartar` |
  | `UserRole` | `especialista`, `admin` |
  | `AccountStatus` | `PENDIENTE_ACTIVACION`, `ACTIVO` |
  | `LesionClass` | `melanoma`, `no_melanoma` (I1) |

  Campos de `AppUser` ← `UsuarioOut`: `role` ← `rol`, `status` ← `estado`,
  `clinicalAccess` ← `acceso_clinico`, `cmp` ← `numero_colegiatura`,
  `termsAcceptedAt` ← `fecha_aceptacion_terminos`. `verificadoPor` no viene (opcional).

## 4. Errores

- [x] **I12. Mapeo de errores.** El backend responde `{"error": {"codigo", "mensaje"}}` con un
  mensaje que se puede mostrar tal cual. `ApiClient` lo traduce a
  [AppException](lib/core/errors/app_exception.dart) con el mismo `code`:

  | `codigo` (HTTP) | En la app |
  |---|---|
  | `unauthenticated` (401) | cerrar sesión y volver al login |
  | `permission-denied` (403) | `PermissionDeniedException(mensaje)` |
  | `consent-required` (409) | `ConsentRequiredException` |
  | `validation-required` (409) | `ValidationRequiredException` |
  | `not-found` (404), `already-exists` (409), `invalid-state` (409), `invalid-image` (422) | `AppException(mensaje, code: codigo)` |
  | `invalid-argument` (422) | `AppException(mensaje)`; trae además `campos` |
  | sin respuesta / tiempo agotado | `AppException('Sin conexión…')` y marcar offline (I21) |

  Las subclases deben aceptar el `mensaje` del backend en vez del texto fijo.

## 5. Identidad y flujos de cuenta

- [ ] **I13. Inicio de sesión.**
  - Fase 1: `DevTokenProvider` con una tabla correo → uid de las cuentas que siembra
    [local.py](../backend/dermavia/local.py) (`admin@dermavia.local` → `admin-dev`,
    `especialista@dermavia.local` → `especialista-dev`, `nuevo@dermavia.local` →
    `especialista-nuevo`). La contraseña no se verifica en el servidor local. Actualizar
    "Cuentas de demostración" del login según el modo.
    **Fase 1 hecha** (`DevTokenProvider`). Las cuentas que el administrador da de alta
    durante la sesión del servidor también pueden entrar: su uid se busca con
    `GET /admin/users` usando la cuenta `admin-dev`. La sesión no se guarda entre
    reinicios de la app.
  - Fase 2: `FirebaseAuth.signInWithEmailAndPassword` y `getIdToken()` en cada petición
    (Firebase lo renueva solo).
  - En ambos casos, después del token se llama `GET /users/me` para obtener el perfil, y el
    error de credenciales sigue siendo genérico (HU04·CA2).
- [x] **I14. Acceso clínico revocado.** `GET /users/me` responde aunque el especialista no
  tenga acceso clínico (el backend solo lo bloquea en las rutas clínicas). La app debe
  cerrar sesión y mostrar el mensaje actual ("Tu acceso clínico fue revocado…") si
  `rol == especialista` y `acceso_clinico == false`.
- [ ] **I15. Alta de especialista y activación de la cuenta.**
  - `POST /admin/specialists` recibe `nombres`, `correo`, `dni`, `numero_colegiatura`,
    `colegiatura_verificada` y `establecimiento` (opcional), y devuelve `UsuarioOut`, **no**
    un `ActivationTicket`. El backend **no envía correo**.
  - Según [identidad.py](../backend/dermavia/dominio/identidad.py), el especialista activa
    la cuenta definiendo su contraseña con el flujo de recuperación de Firebase, y la
    primera petición autenticada marca la cuenta como activa.
  - Cambios: `createSpecialist` devuelve `AppUser`; tras el alta, la app del admin dispara
    `sendPasswordResetEmail(correo)` (fase 2);
    [new_specialist_screen.dart](lib/features/admin/new_specialist_screen.dart) deja de
    mostrar la fecha del enlace; "Tengo un enlace de activación"
    ([login_screen.dart](lib/features/auth/login_screen.dart)) envía el correo de
    restablecimiento; [activation_screen.dart](lib/features/auth/activation_screen.dart) y
    la ruta `/activar/:uid` quedan solo para el modo mock.
  - Fase 1: el alta funciona (crea el perfil en memoria) y la cuenta nueva puede entrar
    con su correo (I13). **Hecho:** `createSpecialist` devuelve `AppUser` y la pantalla
    de alta ya no muestra el vencimiento del enlace. **Pendiente (fase 2):** enviar el
    correo de Firebase; "Tengo un enlace de activación" muestra un aviso con el servidor
    local.
- [ ] **I16. Recuperar contraseña.** `requestPasswordReset` → `sendPasswordResetEmail`
  (fase 2). `resetPassword` y `expireResetLink` no tienen equivalente: la nueva contraseña
  se define en la página de Firebase. Simplificar
  [recover_screen.dart](lib/features/auth/recover_screen.dart) a "te enviamos un enlace" y
  configurar la política de contraseñas (`PasswordPolicy`) en la consola de Firebase. En la
  fase 1, mostrar que la función no está disponible con el servidor local.
  **Fase 1 hecha:** la pantalla muestra el aviso (`kFirebasePending`).

## 6. Flujo del caso y cola offline

- [x] **I17. Envío sin bloquear la pantalla.** `POST /cases/{id}/submit` analiza las fotos
  dentro de la misma petición y puede tardar varios segundos (más en un arranque en frío de
  Cloud Run). `submitCase` debe:
  1. `POST /cases` con `id_paciente`, `datos_clinicos` e `id_solicitud`;
  2. pedir las dos URL de carga y subir las fotos;
  3. devolver el caso (estado `REGISTRADO`) para que
     [clinical_data_screen.dart](lib/features/capture/clinical_data_screen.dart) navegue a
     `/caso/:id/enviado`;
  4. lanzar `submit` en segundo plano.

  [case_submitted_screen.dart](lib/features/case_review/case_submitted_screen.dart) sondea
  `GET /cases/{id}/status` hasta `PENDIENTE_VALIDACION` o `ERROR_ANALISIS`. El backend no
  devuelve `EN_ANALISIS` hasta que empieza el análisis; la app puede mostrarlo como "Enviado".
- [x] **I18. Cola offline persistente (RF-02.4, RNF-08).** Hoy la cola vive en memoria del
  `MockBackend`. En los modos remotos:
  - guardar en el dispositivo el borrador, los datos clínicos, un `id_solicitud` (`uuid`) y
    las fotos copiadas a la carpeta de la app (las de la cámara están en una carpeta temporal);
  - mostrar el caso en el panel con un id local temporal y `queuedOffline: true`;
  - al reconectar, reenviar en orden; el backend es idempotente: el mismo `id_solicitud`
    devuelve el caso ya creado y `submit` no vuelve a analizar un caso ya enviado;
  - cambiar el id local por el del backend y redirigir `/caso/<id local>` al id real.

  **Hecho:** `LocalCaseStore` con `shared_preferences` y fotos copiadas a la carpeta de
  documentos de la app. Si el backend rechaza un caso de la cola (p. ej. consentimiento
  revocado), queda en la cola con el motivo visible; todavía no hay forma de descartarlo
  desde la app.
- [x] **I19. Carga de las fotos.** `POST /cases/{id}/upload-url` con
  `{"vista": "a"|"b", "tipo_contenido": "image/jpeg"|"image/png"}` devuelve `url`, `metodo`
  (`PUT`), `encabezados` y `vence`. Subir con esos encabezados exactos, sin el token de la
  app. Las URL vencen en 15 min: pedirlas justo antes de subir (también al vaciar la cola).
  Solo JPG o PNG de hasta 20 MB; las fotos solo se pueden cargar en `REGISTRADO` o
  `ERROR_ANALISIS`.
- [x] **I20. Orden manual del panel (RF-06.2).** El backend no lo guarda (pendiente en su
  README). `RestCaseRepository` lo guarda en el dispositivo y notifica a `myCasesProvider`.

## 7. Conectividad y notificaciones

- [x] **I21. Conectividad real.** `ConnectivityService` con `connectivity_plus` y con los
  fallos de red de `ApiClient`. El interruptor "Simular sin conexión" de
  [profile_screen.dart](lib/features/profile/profile_screen.dart) queda solo en modo mock o
  en compilaciones de depuración.
- [ ] **I22. Notificaciones push (fase 2).** Pedir permiso, obtener el token de FCM y
  registrarlo con `POST /users/me/devices` (`{"token"}`) al iniciar sesión y cuando cambie.
  La push es genérica y sin datos clínicos; al tocarla, abrir alertas o el caso.

## 8. Android y entorno local

- [x] **I23. Tráfico HTTP en depuración.** Android bloquea `http://` desde la API 28. Agregar
  `android:usesCleartextTraffic="true"` (o una `network_security_config` para `10.0.2.2`)
  **solo** en [android/app/src/debug/AndroidManifest.xml](android/app/src/debug/AndroidManifest.xml).
  El permiso `INTERNET` ya está en el manifiesto principal. Fase 2: `google-services.json` y
  el plugin de Google Services en Gradle.
- [x] **I24. Arranque del servidor local para el emulador.** Las URL firmadas del modo local
  se arman con `DERMAVIA_URL_BASE`; si queda en `localhost` o `0.0.0.0`, el emulador no
  puede subir las fotos. Desde `backend/`, en PowerShell:

  ```powershell
  $env:DERMAVIA_URL_BASE = "http://10.0.2.2:8080"
  .venv\Scripts\python.exe -m dermavia.local --host 0.0.0.0 --puerto 8080
  ```

  o en bash (Linux/macOS):

  ```bash
  DERMAVIA_URL_BASE=http://10.0.2.2:8080 .venv/bin/python -m dermavia.local --host 0.0.0.0 --puerto 8080
  ```

  y en la app:

  ```bash
  flutter run --dart-define=DERMAVIA_BACKEND=local --dart-define=DERMAVIA_API_URL=http://10.0.2.2:8080
  ```

  Cómo crear el entorno del backend en Windows y cómo correr la prueba de extremo a
  extremo: [README.md](README.md#backend-real-servidor-local).

  El servidor necesita el modelo en `../backend/model/` o en
  `../outputs/exp04/20261004T172732Z_registro/` (o `DERMAVIA_MODELO_URI`). En un celular físico, usar la IP de la PC en la red local en
  ambas variables.

## 9. Pruebas

- [x] **I25. Pruebas de la capa remota.**
  - Las pruebas actuales siguen corriendo contra el mock (modo por defecto).
  - DTOs: `fromJson` con ejemplos de JSON reales del backend (caso con y sin predicción,
    validación, informe, usuario, error).
  - `ApiClient`: mapeo de cada `codigo` de I12 con `MockClient` de
    `package:http/testing.dart`.
  - `submitCase`: secuencia completa de peticiones (I17, I19) y reenvío de la cola (I18).
  - Prueba manual de extremo a extremo con el servidor local: alta de paciente →
    consentimiento → caso → predicción → validación → cierre → PDF.
  - `flutter analyze` y `flutter test` en verde antes de cerrar cada paso.

## 10. Orden sugerido

1. Modelos y enums: I11, I1, I2, I3, con el mock y las pruebas ajustados (sin red).
2. Capa remota: I0, I12, I13, I14 y el selector de backend; I23 e I24 para probar.
3. Pacientes (I7) → casos (I4, I5, I6, I17, I19) → validación (I8) → informes (I9).
4. Administración y auditoría (I10, I15 en lo que aplica a la fase 1), cola offline (I18),
   conectividad (I21), orden manual (I20), pruebas (I25).
5. Fase 2: Firebase Auth (I13, I15, I16), FCM (I22) y la URL de Cloud Run.

## 11. Pendientes que dependen del equipo o del backend

- **D1 / A1**: el protocolo de la segunda foto define los nombres finales de las vistas (I3).
- **A3**: el recorte al campo del dermatoscopio en 4:3, ¿en la app o en el backend?
- **Historial del paciente**: `GET /patients/{id}/cases` solo devuelve los casos del médico
  actual, mientras que `GET /patients/{id}/reports` trae los informes cerrados de todos.
  Decidir si [patient_history_screen.dart](lib/features/patients/patient_history_screen.dart)
  combina ambos.
- **PDF en el backend** (`GET /reports/{id}/pdf`): hoy el PDF lo genera la app (I9).
- **RF-07.3**: eliminación o anonimización a pedido del titular (no existe en el backend).
- **Id visible del caso** (I5): correlativo en el backend o id corto en la app.
