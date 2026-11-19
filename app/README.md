# Dermavía · App móvil (v0.1)

Aplicación Android de apoyo diagnóstico para melanoma maligno, de uso exclusivo del
médico especialista y del administrador (tesis TP202620060, UPC). Implementa el flujo
obligatorio **registro → predicción preliminar → validación médica → cierre** de los
mockups `Dermavia-mockups-standalone.html`.

> Esta primera versión funciona con un **backend simulado en memoria**. Las reglas de
> negocio críticas (consentimiento obligatorio, sustento clínico, registro inmutable,
> cierre solo tras validación) se aplican en esa capa, igual que en el backend real.

## Requisitos

- Flutter 3.35 / Dart 3.9
- Android SDK (minSdk 24). Solo se genera la plataforma Android.

```bash
flutter pub get
flutter run            # emulador o dispositivo Android
flutter test           # pruebas unitarias y de widget
flutter build apk      # APK de distribución
```

## Cuentas de demostración

| Rol | Correo | Contraseña |
|---|---|---|
| Médico especialista | `lramirez@hospital.gob.pe` | `Dermavia#2026` |
| Administrador | `admin@hospital.gob.pe` | `Admin#2026!` |
| Especialista con acceso revocado | `rdiaz@hospital.gob.pe` | `Dermavia#2026` |
| Pendiente de activación | `psalas@hospital.gob.pe` | — (usar *Tengo un enlace de activación*) |

En el login, *Cuentas de demostración* rellena los campos. En **Perfil** se puede
**simular sin conexión** para probar la cola de envío diferido (RNF-08).

## Arquitectura

```
lib/
  core/        tema (tokens del mockup), router (redirects por sesión/rol/alcance),
               widgets comunes, ImageQualityService, utilidades
  domain/      modelos (usuario, paciente, caso, predicción, validación, informe,
               auditoría) y contratos de repositorio
  data/mock/   MockBackend + repositorios simulados + datos de ejemplo
  providers/   Riverpod: repository_providers.dart (punto único de cambio) y estado
               del borrador de captura
  features/    auth, dashboard, alerts, patients, capture, case_review,
               validation, reports, admin, profile
```

Los repositorios (`lib/domain/repositories/repositories.dart`) corresponden a los
módulos del backend monolítico modular de la Tabla 6: Identidad, Pacientes, Gestión de
Casos (+ Inferencia), Validación Clínica, Informes y Auditoría.

### Backend real (servidor local)

La app elige el backend al compilar con `--dart-define=DERMAVIA_BACKEND`:

| Valor | Backend |
|---|---|
| `mock` (por defecto) | simulado en memoria, con las cuentas de demostración de arriba |
| `local` | servidor local del backend (`../backend`), con tokens `dev:<uid>` |
| `nube` | Cloud Run + Firebase (fase 2, pendiente) |

El backend necesita **Python 3.12 o 3.13** (`requires-python` de `../backend/pyproject.toml`).
Con [uv](https://docs.astral.sh/uv/), `uv venv --python 3.12` lo descarga si no está instalado.

**Windows (PowerShell)**

```powershell
# 1. Crear el entorno del backend (una sola vez), desde ../backend
cd ..\backend
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -e ".[gcp,dev]"
uv pip install --python .venv\Scripts\python.exe --no-deps -e ..

# 2. Arrancar el servidor para el emulador (las URL de las fotos apuntan a 10.0.2.2)
$env:DERMAVIA_URL_BASE = "http://10.0.2.2:8080"
.venv\Scripts\python.exe -m dermavia.local --host 0.0.0.0 --puerto 8080

# 3. En otra terminal, desde app\
flutter run --dart-define=DERMAVIA_BACKEND=local --dart-define=DERMAVIA_API_URL=http://10.0.2.2:8080
```

`$env:` solo vale para esa terminal; para quitarla: `Remove-Item Env:DERMAVIA_URL_BASE`.
La primera vez, Windows puede pedir permiso en el firewall para que Python acepte
conexiones: hay que permitirlo en redes privadas.

**Linux / macOS / Git Bash**

```bash
cd ../backend
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[gcp,dev]"
uv pip install --python .venv/bin/python --no-deps -e ..
DERMAVIA_URL_BASE=http://10.0.2.2:8080 .venv/bin/python -m dermavia.local --host 0.0.0.0 --puerto 8080
```

En Git Bash sobre Windows, el intérprete está en `.venv/Scripts/python.exe`.

**Prueba de extremo a extremo desde la PC** (sin emulador): arrancar el servidor **sin**
`DERMAVIA_URL_BASE`, para que las URL de las fotos apunten a `127.0.0.1`:

```powershell
# Terminal 1, en ..\backend
Remove-Item Env:DERMAVIA_URL_BASE -ErrorAction SilentlyContinue
.venv\Scripts\python.exe -m dermavia.local --puerto 8080

# Terminal 2, en app\
$env:DERMAVIA_E2E_URL = "http://127.0.0.1:8080"
flutter test test/e2e
```

El servidor busca el modelo (`artefacto.json` y el `.tflite`) en `../backend/model/`,
luego en `../outputs/exp04/20261004T172732Z_registro/` (o en `DERMAVIA_MODELO_URI`); sin él, todo funciona salvo el análisis, que deja el caso en
`ERROR_ANALISIS`.

Cuentas del servidor local (la contraseña no se verifica): `especialista@dermavia.local`,
`admin@dermavia.local` y `nuevo@dermavia.local` (aún no acepta el alcance). En un celular
físico, usa la IP de la PC en `DERMAVIA_URL_BASE` y en `DERMAVIA_API_URL`.
Las diferencias de contrato con el backend de `../backend` y los cambios necesarios están
en [INTEGRACION_BACKEND.md](INTEGRACION_BACKEND.md).

### Estados del caso

`REGISTRADO → EN_ANALISIS → (ERROR_ANALISIS) → PENDIENTE_VALIDACION → VALIDADO → CERRADO`

El backend simulado reprocesa los casos con error cada 20 s (equivalente a Cloud
Scheduler); `CASO-0197` falla en su primer análisis para demostrarlo.

### Modelo

La app **no clasifica** lesiones: la inferencia ocurre en el backend. El simulador
aplica los parámetros del artefacto de EXP-04 (fusión de dos vistas en float16) a una
salida sin calibrar determinista: decide la clase con esa salida (umbral 0.0138) y le
muestra al médico la probabilidad calibrada (isotónica), con la línea de alerta en ~7%.
La app nunca deduce la clase de la probabilidad calibrada: por los escalones de la
calibración, el mismo 7% puede tener o no alerta. El control
local de calidad de imagen (`ImageQualityService`) usa heurísticas —resolución mínima
1024×1024, formato JPG/PNG, luminancia media y varianza del Laplaciano— que se
reemplazarán por el control TFLite descrito en la sección 3.1 de la memoria.

## Pantallas implementadas

| # | Pantalla | HU / RF |
|---|---|---|
| 01 | Inicio de sesión con error genérico | HU02, HU04·CA2, RF-01.1/01.2 |
| 02 | Activación de cuenta | HU01·CA1 |
| 03 | Aceptación del alcance | HU01·CA2, RF-05.3, RNF-06 |
| 04 | Recuperar contraseña (enlace de 30 min) | HU03 |
| 05 | Panel priorizado, filtros, reordenamiento | HU24, HU25, HU30, RF-06.2 |
| 06 | Alertas de casos vencidos (48 h) | HU24, RF-04.5 |
| 07 | Buscar paciente por HC | HU06·CA2, RF-02.5 |
| 08 | Registrar paciente | HU06·CA1 |
| 09 | Consentimiento informado | HU07, RF-02.6 |
| 10–11 | Captura de dos fotos dermatoscópicas de la misma lesión | HU08, HU09, RF-02.1/02.2 |
| 12 | Imágenes de galería validadas | HU10 |
| 13 | Datos clínicos complementarios | HU11, RF-02.3 |
| 14 | Caso enviado / en cola sin conexión | HU12, RF-02.4, RNF-08 |
| 15 | Caso en procesamiento | HU20·CA2 |
| 16 | Revisión con predicción preliminar | HU20, HU29, RF-03.3, RF-06.1 |
| 17 | Registrar validación | HU21, HU22, RF-04.2/04.3 |
| 18 | Caso validado, conducta, observaciones internas | HU23, HU26, HU31 |
| 19 | Informe PDF (vista previa, imprimir, compartir) | HU27, RF-05.5 |
| 20 | Historial del paciente | HU28, RF-05.6 |
| 21 | Alta de especialista | HU04, RF-01.3 |
| 22 | Usuarios, roles y bitácora | HU05, RNF-17 |

## Pendiente para siguientes sprints

- Backend en Cloud Run, Firestore, Cloud Storage (URL firmadas) y Firebase Auth reales.
- Notificaciones push con Firebase Cloud Messaging (las alertas ya se calculan).
- Modelo TFLite local de control de calidad y medición de latencia en Cloud Run.
- Persistencia local de la cola offline (hoy vive en memoria del proceso).
