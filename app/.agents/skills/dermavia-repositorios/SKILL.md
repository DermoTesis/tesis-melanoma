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
           MockXRepository (lib/data/mock)        XRepository real (pendiente)
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
   `StreamProvider` o `StreamProvider.family` para lecturas. Derivados puros (orden,
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
- `MockInferenceEngine.predict` es determinista (hash del caso) y
  `MockInferenceEngine.predictionFor(p, fecha)` construye una `Prediction` concreta para
  pruebas.

## Conectar el backend real

La UI no cambia: consume `Stream`s equivalentes a los listeners de Firestore.

1. Crear `lib/data/remote/` (o `lib/data/firebase/`) con una clase por contrato:
   `FirebaseAuthRepository`, `RestCaseRepository`, etc., que implementen la misma
   interfaz.
2. Mapear errores del backend a `AppException`/subclases con el mismo `code`
   (`auth/invalid-credentials`, `permission-denied`, `consent-required`,
   `validation-required`) para que las pantallas sigan funcionando.
3. Reemplazar `Mock*Repository(...)` por la implementación real en
   `repository_providers.dart`. Mantener `mockBackendProvider` para las pruebas o
   eliminar su uso de `clockProvider`.
4. Las reglas de negocio pasan a validarse en Cloud Run; la app sigue sin clasificar
   lesiones (la inferencia es siempre remota).
5. Pendientes conocidos (README): Firestore, Cloud Storage con URL firmadas, FCM para
   alertas, persistencia local de la cola offline y control TFLite de calidad de imagen
   que reemplace a `ImageQualityService`.
