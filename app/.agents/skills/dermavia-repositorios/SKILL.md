---
name: dermavia-repositorios
description: Cómo añadir o cambiar una operación de datos en Dermavía (contrato en lib/domain/repositories, implementación simulada en lib/data/mock, provider de Riverpod y prueba) y cómo sustituir los Mock*Repository por el backend real (Cloud Run REST + Firebase Auth/Firestore/FCM). Úsala al tocar repositorios, MockBackend, seed_data o al integrar el backend.
---

# Repositorios y backend de Dermavía

## Arquitectura de datos

```
UI (lib/features) ──ref.watch/read──▶ providers (lib/providers)
                                        │  repository_providers.dart = único punto de cambio
                                        ▼
                     contratos (lib/domain/repositories/repositories.dart)
                                        │
                     ┌──────────────────┴──────────────────┐
           MockXRepository (lib/data/mock)        RestXRepository (lib/data/remote)
                     │
               MockBackend: estado en memoria + reglas + watch() tipo Firestore
```

Cada contrato corresponde a un módulo del backend monolítico modular (Tabla 6 de la
memoria): `AuthRepository`/`AdminRepository` (Identidad), `PatientRepository`,
`CaseRepository` (Gestión de Casos + Inferencia), `ValidationRepository`,
`ReportRepository`, `AuditRepository`, más `ConnectivityService`.

## Añadir una operación nueva

1. **Contrato** en [repositories.dart](../../../lib/domain/repositories/repositories.dart):
   firma con parámetros nombrados `required` y doc comment con el requisito
   (`/// ... (RF-xx.y).`). Lecturas como `Stream<T> watchX(...)`; escrituras como
   `Future<T>`.
2. **Modelo** si hace falta, en `lib/domain/models/`: clase inmutable con constructor
   `const`, `copyWith` (con flags `clearX` para anular campos opcionales) y enums con
   extensión `label` en español. Sin dependencias de Flutter en `domain/`.
3. **Implementación simulada** en [mock_repositories.dart](../../../lib/data/mock/mock_repositories.dart),
   en el orden habitual:
   ```dart
   @override
   Future<X> hacerAlgo(String caseId) async {
     await _b.delay();                    // latencia simulada
     final doctor = _b.requireClinician(); // o requireSession / requireAdmin
     final c = _b.cases[caseId];
     if (c == null) throw const AppException('Caso no encontrado.');
     // ...reglas de negocio → AppException con mensaje para el médico
     _b.cases[caseId] = c.copyWith(...);  // reemplaza, no mutes
     _b.log(AuditType.algo, caseId);      // si es auditable
     _b.notify();                          // dispara todos los watch()
     return ...;
   }
   ```
   Lecturas: `Stream<T> watchX() => _b.watch(() => ...)`; ordena y filtra dentro del
   closure y devuelve listas nuevas (`List.unmodifiable` cuando se expone estado
   interno).
4. **Provider** en [repository_providers.dart](../../../lib/providers/repository_providers.dart):
   `StreamProvider.autoDispose` (o `.autoDispose.family`) con `_forSession(...)` para
   lecturas: se vacían sin sesión y no conservan datos de la cuenta anterior. Derivados puros (orden,
   filtros, vencimientos) van en [case_providers.dart](../../../lib/providers/case_providers.dart).
5. **Datos de ejemplo** en [seed_data.dart](../../../lib/data/mock/seed_data.dart) si la
   demo los necesita. No cambies `DemoCredentials` (README y pruebas dependen de ellas).
6. **Prueba** en `test/data/mock_repositories_test.dart` (ver skill [`dermavia-pruebas`](../dermavia-pruebas/SKILL.md)).

Reglas clínicas que deben respetarse: ver skill [`dermavia-reglas-clinicas`](../dermavia-reglas-clinicas/SKILL.md).

## MockBackend: detalles útiles

- `latency` (350 ms), `analysisDuration` (3 s) y `schedulerInterval` (20 s) son
  configurables; las pruebas los ponen en cero/`null`.
- `now()` usa el reloj inyectado; nunca uses `DateTime.now()` dentro de la capa mock.
- IDs: `nextCaseId()` → `CASO-0201`…; `nextId('VAL')` → `VAL-1000`…
- `MockInferenceEngine.predict` es determinista (hash del caso): genera una salida sin
  calibrar y le aplica `ModelArtifact` (parámetros del registro de EXP-04).
  `MockInferenceEngine.fromModelOutput(salida, fecha)` hace lo mismo con una salida dada
  (los casos de `seed_data` se definen así) y
  `MockInferenceEngine.predictionFor(p, fecha, clase: ...)` construye una `Prediction`
  concreta para pruebas, con la clase explícita.

## Backend real (`lib/data/remote/`)

Estado y pendientes en [INTEGRACION_BACKEND.md](../../../INTEGRACION_BACKEND.md). La
UI no cambia: consume los mismos `Stream`s.

- `repository_providers.dart` elige la implementación con
  `--dart-define=DERMAVIA_BACKEND=mock|local|nube` (`backendConfigProvider`). `mock`
  es el valor por defecto y el que usan las pruebas.
- `ApiClient` agrega el token, manda JSON y traduce `{"error": {"codigo", "mensaje"}}`
  a `AppException` con el mismo `code`. Un fallo de red es `NetworkException`.
- `codecs.dart` es el único lugar que conoce el JSON del backend (nombres de campos y
  valores de los enums, p. ej. `melanoma`/`no_melanoma`, vistas `a`/`b`).
- `RefreshHub.watch` arma los `Stream` con REST: lee al suscribirse, cada
  `pollInterval` y tras `notify()`. **Toda escritura en un `Rest*Repository` debe
  llamar `_hub.notify()`**, como `_b.notify()` en el simulado.
- `LocalCaseStore` guarda en el dispositivo la cola offline (con `id_solicitud`), la
  equivalencia id local → id del backend, las fotos de los casos capturados aquí y el
  orden manual del panel.
- `TokenProvider`: `DevTokenProvider` (`dev:<uid>`, servidor local) y
  `FirebaseTokenProvider` (nube, ver [CONEXION_NUBE.md](../../../CONEXION_NUBE.md)), que
  también envía los correos para definir la contraseña (`PasswordLinkSender`). Firebase va
  detrás de interfaces (`FirebaseAuthGateway`, `PushMessaging`) para probarlo sin el plugin.
- La cola offline guarda el uid del médico (`QueuedCase.ownerUid`): solo se muestran y
  envían los casos del usuario con sesión.
- Al añadir una operación: endpoint en `backend/dermavia/presentacion/rutas.py`,
  conversión en `codecs.dart`, método en el `Rest*Repository`, ejemplo JSON en
  `test/data/remote/fixtures.dart` y prueba con `MockClient`.
- Las reglas de negocio las aplica el backend; la app sigue sin clasificar lesiones.
