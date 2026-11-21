# Backend de Dermavía

Monolito modular que se despliega como un único servicio en Cloud Run (southamerica-west1,
2 vCPU, 2 GB, sin GPU, escala a cero). Implementa la sección 5.2 de la memoria v10: la API REST
(capa de presentación), los ocho módulos de dominio de la Tabla 6 y los adaptadores de
infraestructura (Firestore, Cloud Storage, Firebase Authentication y Cloud Messaging, Cloud
Logging). La app Flutter (rama `app`) es el único cliente.

## Estructura

```
dermavia/
  main.py                  aplicación FastAPI (create_app) y formato de errores
  config.py                variables de entorno
  contenedor.py            raíz de composición: módulos + adaptadores según el entorno
  local.py                 servidor local sin Google Cloud
  presentacion/            API REST: autenticación (ID token + rol), esquemas JSON, rutas
  dominio/                 entidades, máquina de estados del caso y los ocho módulos:
    identidad.py             cuentas, roles, aceptación del alcance
    pacientes.py             pacientes y consentimiento informado
    casos.py                 Gestión de Casos: registro, URL firmadas, envío y estados
    inferencia.py            artefacto versionado + LiteRT (melanoma.serving)
    validacion.py            validación clínica de solo inserción
    informes.py              cierre condicionado e informe exportable
    notificaciones.py        alertas push de casos vencidos
    auditoria.py             bitácora y métricas del modelo
  infraestructura/         memoria (pruebas y local), firestore, gcs, firebase, modelo, registro
scripts/                   publicar_modelo.py (HU19) y crear_admin.py (primera cuenta)
tests/                     flujo completo por HTTP, barreras clínicas, inferencia, documentos
```

Los módulos solo se llaman por sus métodos públicos, y el dominio no importa ninguna biblioteca
de la nube: cada servicio externo entra por un puerto (`dominio/puertos.py`) con dos
implementaciones, en memoria y en Google Cloud.

## Decisiones de implementación

- **Python y FastAPI.** El umbral operativo (0.0138) se fijó en EXP-04 leyendo las fotos con
  Pillow y corriendo el `.tflite` con LiteRT (`src/melanoma/serving.py`). EXP-05 mostró que leer
  las fotos con otra biblioteca hace cambiar de clase a algunas lesiones, así que el backend
  importa ese mismo código en vez de reescribirlo en otro lenguaje. Una prueba compara el
  backend con `melanoma.serving` sobre fotos de HAM10000 con el modelo real.
- **La clase la decide el backend** con la salida sin calibrar (≥ 0.0138), como en el registro
  de EXP-04. La respuesta trae la clase, la probabilidad calibrada, la línea de alerta (solo para
  mostrar) y la banda (`sin_alerta`, `baja`, `ambigua`, `alta`); no trae la salida sin calibrar
  ni el umbral, para que la app no pueda recalcular la clase (pendiente A9 de la app).
- **Etiqueta `melanoma` / `no_melanoma`**, no benigno/maligno: es la tarea del modelo
  (melanoma frente a todas las demás clases). La conclusión del informe es "Lesión compatible
  con melanoma" o "Lesión no compatible con melanoma".
- **Fotos `a` y `b`**, con nombres neutros: el modelo es simétrico y el protocolo de la segunda
  foto (D1 de `app/PENDIENTES.md`) no está decidido. Se cargan directo a Cloud Storage con URL
  firmadas V4 (15 min), sin pasar por el backend.
- **Inferencia síncrona** en `POST /cases/{id}/submit`. Si falla, el caso queda en
  `ERROR_ANALISIS` y la tarea de Cloud Scheduler lo reintenta (hasta 5 intentos). También
  retoma los casos que quedaron `EN_ANALISIS` más de 10 min (la instancia se apagó a mitad).
- **Estados**: solo Gestión de Casos cambia el estado, siempre dentro de una transacción y con
  la tabla de transiciones de `dominio/modelos.py`. No existe ninguna transición a `CERRADO` que
  no venga de `VALIDADO` (RF-07.1).
- **Validación inmutable**: base de Firestore aparte (`validaciones`), solo `create`. La
  validación principal tiene id fijo (`<caso>-principal`), así que dos envíos simultáneos no
  pueden crear dos; las siguientes son complementarias (`complementa_de`).
- **Idempotencia para la cola offline (RNF-08)**: la app manda un `id_solicitud` por caso; un
  reenvío devuelve el caso ya creado, y reenviar `submit` no vuelve a analizar.
- **Permisos**: el ID token de Firebase identifica al usuario, pero el rol y el acceso clínico
  se leen del perfil en Firestore en cada solicitud, así que revocar el acceso tiene efecto
  inmediato. Un especialista solo ve sus casos; los informes cerrados (historial del paciente)
  los ve cualquier especialista habilitado.
- **Auditoría**: cada evento crítico va a Cloud Logging como JSON (`tipo_registro: auditoria`)
  y a la colección `auditoria` (pantalla de bitácora del admin). Las validaciones registran la
  concordancia con el modelo y su versión, para la métrica de degradación (RNF-14).
- **Notificaciones**: una push por médico, con texto genérico y sin datos clínicos, cuando un
  caso lleva más de 48 h pendiente desde su predicción. Cada caso se alerta una vez.

## Endpoints

Todos exigen `Authorization: Bearer <ID token de Firebase>`, salvo `/health` y las tareas (token
OIDC de Cloud Scheduler). Los errores llegan como `{"error": {"codigo", "mensaje"}}`, con los
mismos códigos que `AppException` en la app (`permission-denied`, `consent-required`,
`validation-required`, ...). El contrato completo está en `/docs` (OpenAPI).

| Módulo | Endpoints |
|---|---|
| Identidad | `GET /users/me`, `POST /users/me/terms`, `POST /users/me/devices`, `GET /admin/users`, `POST /admin/specialists`, `PATCH /admin/users/{uid}/role`, `GET /admin/audit` |
| Pacientes | `GET /patients[?hc=]`, `POST /patients`, `GET /patients/{id}`, `POST /patients/{id}/consent`, `DELETE /patients/{id}/consent`, `GET /patients/{id}/cases` |
| Gestión de Casos | `POST /cases`, `GET /cases`, `GET /cases/{id}`, `GET /cases/{id}/status`, `POST /cases/{id}/upload-url`, `POST /cases/{id}/submit`, `POST /cases/{id}/notes` |
| Validación Clínica | `GET /cases/pending`, `PUT /cases/{id}/suggestion`, `POST /validations`, `GET /cases/{id}/validations` |
| Informes | `POST /cases/{id}/close`, `GET /reports/{caseId}`, `GET /patients/{id}/reports` |
| Tareas (Cloud Scheduler) | `POST /tasks/reprocess`, `POST /tasks/overdue-alerts` |

Flujo de un caso desde la app: `POST /cases` → `POST /cases/{id}/upload-url` (vista `a` y `b`)
→ `PUT` de cada foto a su URL con el `Content-Type` indicado → `POST /cases/{id}/submit` (devuelve
el caso con su predicción) → `POST /validations` → `POST /cases/{id}/close` → `GET /reports/{id}`.

## Desarrollo local

```bash
cd backend
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[gcp,dev]"
uv pip install --python .venv/bin/python --no-deps -e ..   # melanoma.serving
.venv/bin/python -m pytest                                  # ~3 s
.venv/bin/python -m dermavia.local --puerto 8080            # servidor sin Google Cloud
```

En Windows (PowerShell), el intérprete está en `.venv\Scripts\python.exe` y las variables
de entorno se definen con `$env:`:

```powershell
cd backend
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -e ".[gcp,dev]"
uv pip install --python .venv\Scripts\python.exe --no-deps -e ..
.venv\Scripts\python.exe -m pytest
$env:DERMAVIA_URL_BASE = "http://10.0.2.2:8080"   # solo para usarlo desde el emulador
.venv\Scripts\python.exe -m dermavia.local --host 0.0.0.0 --puerto 8080
```

El servidor local guarda todo en memoria, usa el modelo de `backend/model/` (copia local de
`artefacto.json` y el `.tflite`, fuera de git) o, si no existe, de
`outputs/exp04/20261004T172732Z_registro/`, y acepta `Authorization: Bearer dev:<uid>` con las
cuentas `admin-dev`, `especialista-dev` y `especialista-nuevo` (ver `dermavia/local.py`). Las
URL firmadas apuntan al propio servidor (`/dev/almacen/...`). Con `--host 0.0.0.0` lo puede
usar la app desde un emulador Android (`http://10.0.2.2:8080`). El modo local se niega a
arrancar dentro de Cloud Run.

## Despliegue en Google Cloud

Desplegado el 2026-11-21 en el proyecto `tesis-dermavia`:

| Recurso | Valor |
|---|---|
| Servicio Cloud Run | `dermavia-api` en `southamerica-west1`: https://dermavia-api-432424057783.southamerica-west1.run.app |
| Imagen | `southamerica-west1-docker.pkg.dev/tesis-dermavia/dermavia/backend:<commit>` |
| Firestore | `(default)` y `validaciones`, modo nativo, `southamerica-west1` |
| Buckets | `tesis-dermavia-fotos` (casos) y `tesis-dermavia-modelos` (artefactos) |
| Cuentas de servicio | `dermavia-api` (servicio) y `dermavia-tareas` (Cloud Scheduler) |
| Cloud Scheduler | `dermavia-reprocesar` y `dermavia-alertas-vencidas` en `southamerica-east1` |

Pasos para repetirlo en otro proyecto (PowerShell; `$URL` se conoce antes de desplegar porque
Cloud Run usa `https://<servicio>-<número de proyecto>.<región>.run.app`, y el servicio no arranca
sin `DERMAVIA_TAREAS_AUDIENCIA`):

```powershell
$PROYECTO = "tesis-dermavia"; $REGION = "southamerica-west1"
$NUMERO = gcloud projects describe $PROYECTO --format="value(projectNumber)"
$URL = "https://dermavia-api-$NUMERO.$REGION.run.app"
$SA_API = "dermavia-api@$PROYECTO.iam.gserviceaccount.com"
$SA_TAREAS = "dermavia-tareas@$PROYECTO.iam.gserviceaccount.com"
$IMAGEN = "$REGION-docker.pkg.dev/$PROYECTO/dermavia/backend"; $ETIQUETA = git rev-parse --short HEAD
```

1. Habilitar `run`, `firestore`, `storage`, `cloudscheduler`, `artifactregistry`, `cloudbuild`,
   `iamcredentials`, `firebase`, `identitytoolkit`, `fcm`, `logging` y `firebaserules`
   (`gcloud services enable <api>.googleapis.com ...`).
2. Agregar Firebase al proyecto (consola de Firebase, o `POST
   https://firebase.googleapis.com/v1beta1/projects/<proyecto>:addFirebase`) y, en la consola,
   Authentication → Comenzar → activar correo electrónico/contraseña. Esto último no se puede
   hacer por API sin pasar a Identity Platform.
3. Firestore en modo nativo en `REGION`: `gcloud firestore databases create --location=$REGION`
   y otra vez con `--database=validaciones`. Desplegar `firestore.rules` en ambas (consola, o la
   API de Firebase Rules con las releases `cloud.firestore` y `cloud.firestore/validaciones`).
4. Dos buckets privados en `REGION` (`--uniform-bucket-level-access --public-access-prevention`):
   uno para las fotos de los casos y otro para los modelos.
5. Permisos de `dermavia-api`: `roles/datastore.user`, `roles/firebaseauth.admin`,
   `roles/firebasecloudmessaging.admin` y `roles/logging.logWriter` en el proyecto;
   `roles/storage.objectAdmin` sobre el bucket de fotos; `roles/storage.objectViewer` sobre el de
   modelos; y `roles/iam.serviceAccountTokenCreator` sobre sí misma (para firmar las URL).
6. Publicar el modelo, con credenciales de aplicación (`gcloud auth application-default login`
   y `set-quota-project`):
   `python scripts/publicar_modelo.py --destino gs://<bucket-modelos>/modelos`.
7. Construir la imagen desde la raíz del repo. `.gcloudignore` limita lo que se sube a lo que
   copia el Dockerfile (sin él, gcloud sube `app/build` y `app/.dart_tool`, unos 2 GB). En
   proyectos nuevos la cuenta de Compute que usa Cloud Build necesita
   `roles/cloudbuild.builds.builder`, o la compilación falla al leer la fuente.

   ```powershell
   gcloud artifacts repositories create dermavia --repository-format=docker --location=$REGION
   gcloud projects add-iam-policy-binding $PROYECTO --role roles/cloudbuild.builds.builder `
     --member "serviceAccount:$NUMERO-compute@developer.gserviceaccount.com"
   gcloud builds submit --config backend/cloudbuild.yaml --substitutions "_IMAGEN=$IMAGEN,_ETIQUETA=$ETIQUETA" .
   ```

8. Desplegar:

   ```powershell
   gcloud run deploy dermavia-api --image "${IMAGEN}:$ETIQUETA" --region $REGION `
     --service-account $SA_API --cpu 2 --memory 2Gi --concurrency 4 `
     --min-instances 0 --max-instances 3 --cpu-boost --allow-unauthenticated `
     --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROYECTO,DERMAVIA_BUCKET_IMAGENES=<bucket-fotos>,DERMAVIA_MODELO_URI=gs://<bucket-modelos>/modelos,DERMAVIA_MODELO_VERSION=20261004T172732Z_registro,DERMAVIA_TAREAS_AUDIENCIA=$URL,DERMAVIA_TAREAS_CUENTA=$SA_TAREAS"
   ```

   `--allow-unauthenticated` es correcto: la app llama directo y el servicio valida el ID token
   en cada solicitud (no hay API Gateway en Sudamérica). `--max-instances 3` acota el gasto.
   `GET /health` debe devolver la versión del modelo: se carga al arrancar.
9. Cloud Scheduler, con token OIDC de `dermavia-tareas` y audiencia `$URL`:
   `POST /tasks/reprocess` cada 5 min y `POST /tasks/overdue-alerts` cada hora. Cloud Scheduler
   no existe en `southamerica-west1`; las tareas viven en `southamerica-east1` y llaman al
   servicio en Santiago.

   ```powershell
   gcloud scheduler jobs create http dermavia-reprocesar --location southamerica-east1 `
     --schedule "*/5 * * * *" --time-zone "America/Lima" --http-method POST `
     --uri "$URL/tasks/reprocess" --oidc-service-account-email $SA_TAREAS --oidc-token-audience $URL
   ```

10. Primera cuenta de administrador: `python scripts/crear_admin.py ...` (también con
    credenciales de aplicación). Imprime el enlace para definir la contraseña.
11. Pendiente: Cloud Logging, un sink de `jsonPayload.tipo_registro="auditoria"` a un bucket de
    registros con retención bloqueada (irreversible), y una métrica basada en registros con
    `jsonPayload.evento.detalle` de las validaciones (concordancia por `version_modelo`).

Cambiar de modelo = publicar la versión nueva y actualizar `DERMAVIA_MODELO_VERSION`
(`gcloud run services update dermavia-api --region southamerica-west1 --update-env-vars ...`),
sin reconstruir la imagen (RNF-13). Para pausar las tareas: `gcloud scheduler jobs pause
<tarea> --location southamerica-east1`.

## Diferencias con la memoria v10 (para actualizar los documentos)

- Endpoints agregados a los de la Tabla 6: `GET /users/me`, `POST /users/me/devices`,
  `GET /admin/users`, `GET /admin/audit`, `DELETE /patients/{id}/consent`,
  `GET /patients/{id}/cases`, `GET /cases`, `GET /cases/{id}`, `PUT /cases/{id}/suggestion`,
  `POST /cases/{id}/notes`, `GET /cases/{id}/validations`, `POST /cases/{id}/close` y las tareas.
  `PATCH /admin/users/{id}/role` también cambia el acceso clínico.
- Esquema: `usuarios` es plano (sin el mapa `metadatos_rol`); `casos.urls_imagenes_storage`
  pasa a `imagenes` con claves `a` y `b`; `prediccion_ml` agrega la salida sin calibrar, el
  umbral, la línea de alerta, el sha256 y la latencia; las observaciones internas viven en el
  caso (`notas_internas`), no en la validación; se agrega la colección `historias_clinicas`
  (unicidad de la HC) y `auditoria`.
- La "base de solo inserción" se garantiza en la aplicación (el repositorio solo usa `create`)
  y con reglas que niegan el acceso de clientes; IAM de Firestore no permite dar solo permiso de
  crear a una cuenta de servicio.

## Pendiente

- Medir los umbrales de EXP-05 en Cloud Run (p95 por caso, cuatro casos simultáneos, arranque
  en frío).
- Probar el flujo completo de un caso contra el proyecto real (Firestore, URL firmadas de Cloud
  Storage, inferencia). Hasta ahora en la nube se comprobó `/health` con el modelo cargado
  desde el bucket, el alta del administrador, `GET /users/me` con un ID token real y las dos
  tareas de Cloud Scheduler.
- Configurar el sink de auditoría en Cloud Logging (paso 11 del despliegue).
- `GET /reports/{caseId}/pdf`: hoy el backend entrega el contenido del informe y la app genera
  el PDF (como en el prototipo).
- Recorte al campo del dermatoscopio en 4:3 antes del modelo (A3 de la app): decidir si va en la
  app o aquí. Hoy se redimensiona la foto entera, como en el entrenamiento.
- Orden manual del panel (RF-06.2) persistido en el backend; hoy no se guarda.
- Eliminación o anonimización a pedido del titular (RF-07.3).
