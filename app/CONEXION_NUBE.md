# Conexión de la app con el backend desplegado (fase 2)

Revisión del 2026-11-21. El backend ya está desplegado en Google Cloud (proyecto
`tesis-dermavia`, ver [backend/README.md](../backend/README.md#despliegue-en-google-cloud)) y su
flujo completo se verificó contra la nube con ID tokens reales de Firebase. Este documento
lista lo que falta en la app para usarlo: el modo `nube`.

Complementa [INTEGRACION_BACKEND.md](INTEGRACION_BACKEND.md), donde está la fase 1 (servidor
local, ya implementada) y donde quedaron abiertas las partes de Firebase de I13, I15, I16 e
I22. Aquí se detallan esas partes y lo que exige el entorno real. Las rutas son relativas a
`app/`.

Leyenda: **N** = cambio para el modo `nube`; **C** = configuración en la consola de Firebase o
de Google Cloud (sin código). Los ids **I** son los de INTEGRACION_BACKEND.md.

## Qué hay desplegado

| Elemento | Valor |
|---|---|
| URL de la API | `https://dermavia-api-432424057783.southamerica-west1.run.app` (documentación en `/docs`) |
| Proyecto de Firebase | `tesis-dermavia`, con Authentication por correo y contraseña habilitado |
| Apps registradas en Firebase | Android `pe.edu.upc.dermavia` (app id `1:432424057783:android:33d690028819e52d21c632`, C1) |
| Cloud Run | `southamerica-west1`, 0 a 3 instancias, 4 solicitudes simultáneas por instancia. Sin instancias mínimas: la primera solicitud tras un rato sin uso arranca una instancia (arranque en frío) |
| Firestore | Reglas que niegan todo acceso de clientes: la app solo habla con la API REST |
| Fotos | Bucket privado; la app sube y lee con URL firmadas V4 que vencen en 15 min |
| Cloud Messaging | API `fcm.googleapis.com` habilitada. La tarea `dermavia-alertas-vencidas` corre cada hora y avisa de los casos que llevan más de 48 h sin validar |
| Cuentas de demostración | Las cuatro del modo mock (`admin@`, `lramirez@`, `rdiaz@` y `psalas@hospital.gob.pe`) con los mismos roles y estados. Las contraseñas **no** son las de [seed_data.dart](lib/data/mock/seed_data.dart) (el repositorio es público) y no se guardan en el repo |

## Qué no cambia

La capa REST de la fase 1 funciona igual contra Cloud Run. Ya se probó con el backend real
(2026-11-21):

- los repositorios REST, los codecs y el mapeo de errores (I0 a I12);
- la carga de fotos con URL firmadas: `PUT` directo a `storage.googleapis.com` con el
  `Content-Type` exacto de `encabezados` y sin el token de la app (I19);
- el envío y la inferencia: unos 0.5 s con la instancia ya arrancada. Con las fotos de
  `../imagenes_prueba/1_HAM_0001974_melanoma_alto` da el mismo resultado que en local
  (melanoma, 75 %, banda alta);
- la idempotencia del reenvío con el mismo `id_solicitud` (cola offline, I18);
- las barreras clínicas: sin consentimiento, sin alcance aceptado y con acceso clínico
  revocado.

La API usa HTTPS, así que el permiso de tráfico HTTP del manifiesto de depuración (I23) solo
sigue haciendo falta para el servidor local.

Lo que faltaba era la identidad. **Estado (2026-11-21):** el código de N1 a N10 y las
pruebas de N12 están hechos; en modo `nube` el `TokenProvider` es `FirebaseTokenProvider`
([token_provider.dart](lib/data/remote/token_provider.dart)). C1 y C3 se hicieron el mismo
día, y las pruebas en un celular físico (N11, N13) pasaron. Todo el plan está completo;
solo queda, opcional, la plantilla de correo propia si el soporte de Firebase la habilita
(C2).

## 1. Consola de Firebase y Google Cloud

- [x] **C1. Registrar la app Android en Firebase.** Hecho (2026-11-21) con la API de
  administración de Firebase y las credenciales de `gcloud`, porque la sesión guardada de la
  CLI de Firebase estaba vencida. El resultado es el mismo que el de `flutterfire configure`:
  [firebase_options.dart](lib/firebase_options.dart), `android/app/google-services.json` y
  el plugin `com.google.gms.google-services` 4.6.0 en Gradle. La API key responde a
  Identity Toolkit (inicio de sesión con correo y contraseña habilitado).
  - Paquete `pe.edu.upc.dermavia` (el `applicationId` de
    [android/app/build.gradle.kts](android/app/build.gradle.kts)).
  - Lo más simple es `flutterfire configure --project=tesis-dermavia --platforms=android`
    (requiere la CLI de Firebase). Registra la app, genera `lib/firebase_options.dart` y
    `android/app/google-services.json`, y agrega el plugin de Google Services a Gradle.
  - Para correo y contraseña no hace falta registrar la huella SHA-1. Sí hará falta si
    después se usa App Check o se restringe la API key a la app (C3).
  - Los dos archivos generados tienen la API key web del proyecto. Es pública por diseño
    (identifica el proyecto, no da acceso a datos) y se pueden subir al repo. La protección
    real es que la API exige un ID token y Firestore niega el acceso de clientes.
- [x] **C2. Correos de activación y recuperación.** Los dos flujos usan la plantilla de
  "restablecer contraseña" de Firebase (I15, I16), que estaba en inglés por defecto.
  **Hecho (2026-11-21)** dentro de lo que Firebase permite: correo en español con el asunto
  "Cambia la contraseña de Dermavía"; la plantilla propia queda opcional (ver abajo).
  - En Authentication → Plantillas: poner "Dermavía" como nombre público del proyecto (es el
    `%APP_NAME%` de la plantilla) y redactar un texto en español que sirva para los dos casos
    (por ejemplo, "Define tu contraseña de Dermavía"). Si solo se cambia el idioma, el correo
    de una cuenta nueva diría "restablece tu contraseña", lo que confunde.
  - Los correos salen de `noreply@tesis-dermavia.firebaseapp.com` y pueden caer en spam.
    Avisar antes de la demo.
  - Los enlaces vencen en **1 hora** (en el mock, el enlace de activación dura 24 h).
  - **Estado (2026-11-21):** el idioma por defecto ya es `es` (por API). La plantilla está
    redactada en [firebase/plantilla_restablecer_contrasena.html](firebase/plantilla_restablecer_contrasena.html):
    sirve para la activación y para la recuperación, explica los pasos (definir la
    contraseña, volver a la app, aceptar el alcance en el primer acceso) y escribe
    "Dermavía" sin usar `%APP_NAME%`.
  - **Firebase no deja editar las plantillas de este proyecto**, ni por API
    (`EMAIL_TEMPLATE_UPDATE_NOT_ALLOWED`) ni en la consola ("Por el momento, no se pueden
    actualizar las plantillas…"); solo el soporte de Firebase puede habilitarlo. **Decisión
    (2026-11-21):** usar por ahora el texto por defecto de Firebase en español (asunto
    "Cambia la contraseña de %APP_NAME%") y explicarlo en la app: el alta del especialista,
    "Tengo un enlace de activación" y la recuperación indican el asunto del correo
    (`kFirebaseEmailSubject` en [auth_widgets.dart](lib/features/auth/auth_widgets.dart)),
    aclaran que en una cuenta nueva es el enlace de activación y recuerdan revisar spam.
  - Nombre público `Dermavía` (el `%APP_NAME%` del correo): hecho. No hay un campo en
    Firebase hasta que existe la pantalla de consentimiento de OAuth; se configuró en Google
    Cloud → Pantalla de consentimiento de OAuth (nombre de la app `Dermavía`, público
    *Interno*). No afecta los correos ni el login con correo y contraseña; solo limitaría un
    futuro "Iniciar sesión con Google" a cuentas de la organización. Comprobado: el correo
    llega con el asunto "Cambia la contraseña de Dermavía".
  - Opcional: pedir al soporte de Firebase que habilite las plantillas. Si lo hace, en
    Authentication → Plantillas → Restablecimiento de contraseña → editar: remitente
    `Dermavía`, asunto `Define tu contraseña de Dermavía` y el HTML de la plantilla;
    comprobar con `python firebase/verificar_plantilla.py` (desde `app/`, con gcloud en el
    PATH) y actualizar `kFirebaseEmailSubject`.
  - Alternativa si el texto genérico no sirve: que el backend genere el enlace con
    `firebase_admin` y envíe su propio correo (requiere un servicio de correo, un endpoint
    de recuperación con límite de intentos y un nuevo despliegue).
- [x] **C3. Restringir la API key.** Hecho (2026-11-21): la key de la app ("Android key
  (auto created by Firebase)", la de `google-services.json`) quedó limitada a Identity
  Toolkit, Token Service, Firebase Installations y FCM Registration. Los scripts de la PC
  usan otra key ("Browser key"), que no cambió. No se limitó a la app Android (paquete y
  SHA-1): la llave de depuración es distinta en cada PC del equipo y las compilaciones de
  otras máquinas dejarían de iniciar sesión. Si se hace, registrar la SHA-1 de cada
  integrante y la de publicación.
- [x] **C4. Instancias mínimas: se quedan en 0** (decisión del 2026-11-21). Sin instancias
  encendidas no hay costo fijo, pero la primera solicitud después de unos minutos sin uso
  espera el arranque del contenedor y la carga del modelo. La app absorbe esa espera con el
  tiempo de espera de N3. El tiempo real del arranque en frío está pendiente de medir
  (EXP-05, README del backend).

## 2. Dependencias y arranque

- [x] **N1. Paquetes y Gradle.** Hecho: `firebase_core` 5.2, `firebase_auth` 7.1 y
  `firebase_messaging` 17.1 y el plugin de Google Services 4.6.0 (C1); el APK de
  depuración compila con AGP 9.1 y Kotlin 2.4.
  - Agregar `firebase_core`, `firebase_auth` y `firebase_messaging` (N9) a
    [pubspec.yaml](pubspec.yaml).
  - Plugin `com.google.gms.google-services` en
    [settings.gradle.kts](android/settings.gradle.kts) y en
    [app/build.gradle.kts](android/app/build.gradle.kts); `flutterfire configure` lo agrega.
  - Comprobar que las versiones de los plugins compilan con AGP 9.1 y Kotlin 2.4, que son
    recientes. `minSdk = 24` alcanza.
- [x] **N2. Inicializar Firebase solo en modo `nube`.** En [main.dart](lib/main.dart), dentro
  del bloque `if (config.isRemote)`, cuando `config.mode == BackendMode.nube`:
  `await Firebase.initializeApp(options: DefaultFirebaseOptions.currentPlatform)` y
  `FirebaseAuth.instance.setLanguageCode('es')`. Los modos `mock` y `local`, y por tanto las
  pruebas, no deben depender de Firebase.
- [x] **N3. URL y tiempos de espera del modo `nube`.** Hecho: `BackendConfig.forMode`
  (45 s en la nube; el botón de login ya muestra que está cargando). En
  [backend_config.dart](lib/data/remote/backend_config.dart):
  - si el modo es `nube` y no se pasa `DERMAVIA_API_URL`, usar la URL de Cloud Run en vez de
    `http://10.0.2.2:8080`. Así basta con
    `flutter run --dart-define=DERMAVIA_BACKEND=nube`;
  - `requestTimeout` (20 s) puede quedarse corto en un arranque en frío, por ejemplo en el
    primer `GET /users/me` del login. Como no habrá instancias encendidas (C4), subirlo para
    el modo `nube` (unos 45 s) y ajustarlo cuando EXP-05 mida el arranque. Mientras espera,
    el login debe mostrar que está cargando, no un error. `analysisTimeout` (120 s) alcanza:
    Cloud Run corta a los 300 s.
  - Actualizar el comentario de la clase: el modo `nube` deja de estar pendiente.

## 3. Inicio de sesión (I13, I14)

- [x] **N4. `FirebaseTokenProvider`** en [token_provider.dart](lib/data/remote/token_provider.dart),
  que reemplaza a `_FirebasePendingTokenProvider` en el caso `BackendMode.nube` de
  `tokenProviderProvider`.
  - `signIn`: `signInWithEmailAndPassword` y devolver el `uid`. Errores de
    `FirebaseAuthException`:

    | `code` | En la app |
    |---|---|
    | `invalid-credential`, `wrong-password`, `user-not-found`, `invalid-email`, `user-disabled` | `AuthException` genérica (HU04·CA2). Una cuenta pendiente todavía no tiene contraseña y cae aquí |
    | `too-many-requests` | `AppException('Demasiados intentos. Espera unos minutos…')` |
    | `network-request-failed` | el mismo error de "sin conexión" de `ApiClient` (I12, I21) |

  - `token()`: `FirebaseAuth.instance.currentUser?.getIdToken()`. Firebase renueva el token
    solo, antes de que venza a la hora. Si la renovación falla porque el administrador cambió
    el rol o quitó el acceso clínico (el backend revoca las sesiones,
    [identidad.py](../backend/dermavia/dominio/identidad.py)), devolver `null` y dejar que el
    401 cierre la sesión (`onUnauthenticated`).
  - `signOut`: `FirebaseAuth.instance.signOut()`.
  - Encapsular `FirebaseAuth` detrás de una interfaz pequeña, para probar el mapeo de errores
    sin Firebase (N12). Hecho: `FirebaseAuthGateway`. Otros códigos de Firebase dan un error
    distinto del de credenciales (`auth/<code>`), y una renovación fallida por falta de red
    da el error de "sin conexión" en vez de cerrar la sesión.
  - [RestAuthRepository.signIn](lib/data/remote/rest_repositories.dart) no cambia: después del
    token pide `GET /users/me`, que activa la cuenta pendiente, y aplica la regla del acceso
    revocado (I14). Las dos cosas se verificaron en la nube con las cuentas de demo.
- [x] **N5. Pedir el login cada vez que se abre la app** (decisión del 2026-11-21, por
  seguridad). Firebase guarda la sesión en el dispositivo y `RestAuthRepository` arranca sin
  usuario (`_user = null`). Sin cambios, la app pediría el login con una sesión de Firebase
  todavía abierta, que además seguiría renovando tokens.
  - En [main.dart](lib/main.dart), justo después de `Firebase.initializeApp` (N2), llamar
    `await FirebaseAuth.instance.signOut()`. Así la sesión de Firebase y la de la app empiezan
    y terminan juntas.
  - **Consecuencia para la cola offline:** iniciar sesión en Firebase necesita conexión. Si
    el médico abre la app sin red, no puede entrar, así que tampoco puede registrar casos
    para la cola. Los casos que ya estaban en la cola no se pierden (están en
    `LocalCaseStore`) y se envían después del siguiente login con conexión. El trabajo sin
    red (RF-02.4) sigue funcionando mientras la app no se cierre.
  - **La cola no sabe de quién es cada caso.**
    [local_case_store.dart](lib/data/remote/local_case_store.dart) guarda los casos
    pendientes sin el `uid` del médico. Si un médico deja casos en la cola, cierra la app y
    otro entra en el mismo celular, esos casos se enviarían con la identidad del segundo.
    Guardar el `uid` en `QueuedCase`, y que el panel y el reenvío
    ([rest_repositories.dart](lib/data/remote/rest_repositories.dart)) solo usen los casos
    del usuario con sesión. Los demás esperan a que su dueño vuelva a entrar. Hecho:
    `QueuedCase.ownerUid`; los casos guardados antes de este cambio (sin dueño) los puede
    enviar cualquier sesión.
- [x] **N6. "Cuentas de demostración" del login: solo los correos** (decisión del
  2026-11-21) ([login_screen.dart](lib/features/auth/login_screen.dart)).
  - En modo `nube` la hoja de "Cuentas de demostración" lista los cuatro correos con su rol
    y su estado (Lucía, Raúl, administrador y Pedro pendiente). Tocar uno completa solo el
    correo y el médico escribe la contraseña. No mostrar `DemoCredentials.*Password` en este
    modo; esas contraseñas solo valen en el mock.
  - Las contraseñas reales no van en el código ni en `--dart-define`: las reparte el equipo
    fuera del repo.
  - La cuenta pendiente es `psalas@hospital.gob.pe`. Su enlace de activación se genera justo
    antes de la demo (vence en 1 h), con el comando de la sección 6.

## 4. Activación y recuperación de la cuenta (I15, I16)

- [x] **N7. Correo de activación tras el alta.** Cuando `POST /admin/specialists` responde 201,
  la app del administrador llama `FirebaseAuth.instance.sendPasswordResetEmail(email: correo)`.
  El backend no envía correos.
  - Esa llamada no cambia la sesión del administrador.
  - Si el correo falla, la cuenta ya existe: mostrar "Cuenta creada, pero no se pudo enviar
    el correo" y ofrecer "Reenviar enlace", por ejemplo en la ficha del especialista de
    [admin_home_screen.dart](lib/features/admin/admin_home_screen.dart). Hecho:
    `ActivationEmailException` y `AdminRepository.resendActivationLink`, con un botón en la
    fila de cada cuenta pendiente.
  - [new_specialist_screen.dart](lib/features/admin/new_specialist_screen.dart): el texto
    final debe decir que el enlace llega por correo y vence en 1 hora.
- [x] **N8. "Tengo un enlace de activación" y "Recuperar contraseña".** Las dos opciones
  llaman a `sendPasswordResetEmail` y muestran "Si la cuenta existe, te enviamos un enlace".
  - Firebase no avisa si el correo no existe (protección contra enumeración de cuentas,
    activa por defecto), y eso coincide con el error genérico de HU04·CA2.
  - La contraseña se define en la página de Firebase; después el médico vuelve a la app e
    inicia sesión, y su primera solicitud activa la cuenta.
  - Cambios en el contrato de [repositories.dart](lib/domain/repositories/repositories.dart):
    `requestPasswordReset` hoy devuelve un `PasswordResetTicket` del mock. En el modo `nube`
    no hay ticket: cambiar la firma a `Future<void>`, o devolver un ticket sin vencimiento.
    Hecho: ticket sin vencimiento (`PasswordResetTicket.opensInApp == false`).
  - **Límite de envíos** (agregado el 2026-11-21): además del límite de Firebase en el
    servidor (`too-many-requests`), la app espera 60 s entre enlaces al mismo correo y
    permite 5 enlaces cada 15 min desde el dispositivo (`PasswordLinkThrottle`, en
    `FirebaseTokenProvider.sendPasswordLink`). Aplica a la recuperación, a "Tengo un enlace
    de activación" y al alta y reenvío del administrador; cuenta igual exista o no la
    cuenta, y un envío fallido no cuenta. La pantalla de recuperación muestra
    "Reenviar enlace en N s". Vive en memoria: reiniciar la app lo borra.
    `findActivation`, `getActivation`, `activateAccount`, `resetPassword` y `expireResetLink`
    quedan solo para el mock, igual que la ruta `/activar/:uid` y
    [activation_screen.dart](lib/features/auth/activation_screen.dart).
  - [recover_screen.dart](lib/features/auth/recover_screen.dart) se reduce a pedir el correo
    y confirmar el envío. Quitar `kFirebasePending` de los flujos que ya funcionan.
  - **Política de contraseñas: el mínimo de Firebase, 6 caracteres** (decisión del
    2026-11-21). No se activa Identity Platform. La app no valida la contraseña porque se
    escribe en la página de Firebase.

## 5. Notificaciones push (I22)

- [x] **N9. Registro del dispositivo.** Hecho: `DeviceRegistration`
  ([push_messaging.dart](lib/data/remote/push_messaging.dart)). Usa `getToken`, que
  firebase_messaging 17 marca obsoleto: su reemplazo entrega el Firebase Installation ID y
  el backend envía con tokens de registro.
  Además, al abrir la app se borra el token que quedó de la última vez (como la sesión de
  Firebase, N5): si un médico cerró la app sin cerrar sesión, el siguiente que entre en el
  mismo celular no registra ese token y no recibe las alertas del anterior. El registro
  espera a que termine ese borrado. Queda una ventana inevitable: mientras la app siga
  cerrada, el celular puede recibir alertas del último médico (sin datos clínicos).
  - Después de cada login, pedir el permiso de notificaciones
    (Android 13+: `POST_NOTIFICATIONS`, que va en el
    [manifiesto](android/app/src/main/AndroidManifest.xml)), obtener
    `FirebaseMessaging.instance.getToken()` y mandarlo con `POST /users/me/devices`
    (`{"token"}`). Volver a mandarlo en `onTokenRefresh`. Solo para especialistas: el
    administrador no recibe alertas.
  - Al cerrar sesión, llamar `FirebaseMessaging.instance.deleteToken()`. El backend no tiene
    un endpoint para quitar un dispositivo, pero borra los tokens inválidos la siguiente vez
    que envía una alerta. Sin esto, el celular seguiría recibiendo las alertas del médico
    anterior.
- [x] **N10. Al tocar la notificación.** Hecho: `PushNotifications`
  ([push_providers.dart](lib/providers/push_providers.dart)); si no hay sesión, `/alertas`
  se abre después del login. La push trae `{"tipo": "casos_vencidos"}` y un texto
  genérico sin datos clínicos
  ([notificaciones.py](../backend/dermavia/dominio/notificaciones.py)). Con
  `getInitialMessage` (app cerrada) y `onMessageOpenedApp` (en segundo plano), abrir
  `/alertas`. Con la app abierta, Android no muestra la notificación: refrescar el panel o
  mostrar un aviso dentro de la app.
- [x] **N11. Prueba de las push.** Hecho (2026-11-21): con la app abierta, en segundo plano
  y cerrada; y un segundo médico en el mismo celular no hereda el token del anterior. La tarea horaria solo alerta casos que de verdad pasaron
  las 48 h. Para probar la recepción sin esperar, enviar un mensaje de prueba al token desde
  la consola de Firebase (Messaging → "Enviar mensaje de prueba"). Para forzar una pasada de
  la tarea: `gcloud scheduler jobs run dermavia-alertas-vencidas --location southamerica-east1`.
  Más simple: `python firebase/enviar_push_prueba.py <correo>` (desde `app/`, con gcloud en el
  PATH) envía a los dispositivos de esa cuenta el mismo mensaje que la tarea horaria;
  `--validar` solo comprueba los tokens. Probar con la app abierta (aviso dentro de la app
  con "Ver"), en segundo plano y cerrada (al tocar la notificación se abre `/alertas`,
  después del login si la app estaba cerrada).

## 6. Pruebas

- [x] **N12. Automáticas.** Hecho: `token_provider_test.dart`, `push_messaging_test.dart`,
  `login_cloud_test.dart` y las pruebas nuevas de la cola y del alta en
  `rest_repositories_test.dart`. Siguen corriendo en modo mock. Agregar pruebas de
  `FirebaseTokenProvider` con un `FirebaseAuth` falso (la interfaz de N4) que cubran la tabla
  de errores de N4 y la renovación fallida. `flutter analyze` y `flutter test` en verde.
- [x] **N13. Manual de extremo a extremo, en un celular físico** (hecho, 2026-11-21) con
  `--dart-define=DERMAVIA_BACKEND=nube`:
  1. Lucía (`lramirez@`): login → paciente → consentimiento → caso con las fotos `_1024` de
     `../imagenes_prueba/1_HAM_0001974_melanoma_alto` (desde la galería) → "Posible melanoma ·
     riesgo 75 %" → validar → cerrar → PDF con las dos fotos.
  2. Modo avión durante el envío → el caso queda en la cola → al reconectar se envía una sola
     vez.
  3. Raúl (`rdiaz@`): el login muestra "Tu acceso clínico fue revocado…".
  4. Administrador (`admin@`): alta de un especialista con un correo real de alguien del
     equipo → llega el correo → define la contraseña → entra → acepta el alcance.
  5. Cerrar y reabrir la app → pide el login otra vez (N5). Con un caso en la cola, entrar
     con otra cuenta → el caso no aparece ni se envía; volver a entrar con la primera → se
     envía.
  6. Push de prueba (N11) → al tocarla se abre `/alertas`.

  Para generar el enlace de activación de Pedro (`psalas@`, desde `../backend` en PowerShell):

  ```powershell
  .venv\Scripts\python -c "import firebase_admin; from firebase_admin import auth; firebase_admin.initialize_app(options={'projectId':'tesis-dermavia'}); print(auth.generate_password_reset_link('psalas@hospital.gob.pe'))"
  ```

## 7. Decisiones tomadas (2026-11-21)

| Tema | Decisión | Dónde aplica |
|---|---|---|
| Sesión al reabrir la app | Pedir el login siempre, por seguridad | N5 |
| Política de contraseñas | El mínimo de Firebase (6 caracteres), sin Identity Platform | N8 |
| Instancias mínimas de Cloud Run | Se quedan en 0; la app tolera el arranque en frío | C4, N3 |
| Contraseñas de demo en la app | Solo se muestran los correos | N6 |
| Datos de prueba en la nube | Se conservan: el "Especialista de Prueba (despliegue)", el paciente `PRUEBA-082800` y su caso cerrado | — |

## 8. Orden sugerido

1. C1 y C2 en la consola; N1, N2 y N3.
2. N4, N5 y N6 → probar el login con las cuentas de demo (pasos 1, 3 y 5 de N13).
3. N7 y N8 (activación y recuperación) → paso 4 de N13.
4. N9–N11 (push).
5. N12, el resto de N13 y C3 antes de la demo. Marcar I13, I15, I16 e I22 en
   INTEGRACION_BACKEND.md.
