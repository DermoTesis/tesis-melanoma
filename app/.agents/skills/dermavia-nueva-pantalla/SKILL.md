---
name: dermavia-nueva-pantalla
description: Cómo crear o modificar una pantalla de la app Flutter de Dermavía siguiendo sus convenciones (feature folder, ConsumerWidget + Riverpod, go_router con redirects por rol, tokens de color del mockup, widgets comunes, textos en español y trazabilidad HU/RF). Úsala al añadir una pantalla, una ruta o una acción de UI en lib/features.
---

# Crear o modificar una pantalla en Dermavía

## 1. Ubicación y cabecera

- Archivo en `lib/features/<módulo>/<nombre>_screen.dart`. Módulos existentes: `auth`,
  `dashboard`, `alerts`, `patients`, `capture`, `case_review`, `validation`, `reports`,
  `admin`, `profile`. Widgets compartidos del módulo van en `<módulo>_widgets.dart`.
- Comentario de clase con número de pantalla del mockup y requisitos:
  ```dart
  /// Pantalla 06 · Alertas de casos vencidos sin validación (HU24, RF-04.5).
  class AlertsScreen extends ConsumerWidget {
  ```
- Si la pantalla es nueva, añade su fila a la tabla **Pantallas implementadas** del
  [README.md](../../../README.md) con su número, HU y RF.

## 2. Estado y datos (Riverpod 3)

- Usa `ConsumerWidget`; `ConsumerStatefulWidget` solo si hay estado local (formularios,
  flags `_saving`).
- Lee datos **solo** a través de los providers de
  [repository_providers.dart](../../../lib/providers/repository_providers.dart)
  (`caseProvider(id)`, `patientsProvider`, `validationsProvider(id)`, …) o
  [case_providers.dart](../../../lib/providers/case_providers.dart). Nunca importes
  `lib/data/mock/` desde una pantalla.
- Para `AsyncValue` sigue el patrón:
  ```dart
  body: caseAsync.when(
    loading: () => const LoadingView(),
    error: (e, _) => ErrorView('$e'),
    data: (c) => c == null ? const ErrorView('Caso no encontrado.') : _Body(c),
  ),
  ```
- La hora actual sale de `ref.watch(clockProvider)()`, no de `DateTime.now()`.

## 3. Acciones que llaman al repositorio

```dart
Future<void> _submit() async {
  setState(() => _saving = true);
  try {
    await ref.read(caseRepositoryProvider).addInternalNote(id, text);
    if (mounted) showAppSnack(context, 'Observación guardada.');
  } on AppException catch (e) {
    if (mounted) showAppSnack(context, e.message, error: true);
  } finally {
    if (mounted) setState(() => _saving = false);
  }
}
```

- Captura `AppException` y muestra su `message` tal cual; no inventes otro texto.
- No dupliques en la UI la validación de reglas de negocio: la capa de datos es la
  fuente de verdad (ver skill [`dermavia-reglas-clinicas`](../dermavia-reglas-clinicas/SKILL.md)). La UI puede deshabilitar
  botones, pero el backend debe seguir rechazando.

## 4. Navegación (go_router)

- Registra la ruta en [app_router.dart](../../../lib/core/router/app_router.dart). Rutas
  en español y en minúsculas (`/caso/:id/validar`, `/paciente/:id/consentimiento`).
- Las pestañas del especialista (`/casos`, `/pacientes`, `/alertas`, `/perfil`) viven en
  el `StatefulShellRoute`; el resto son rutas de nivel superior que se abren con
  `context.push`.
- El `redirect` global ya aplica: sin sesión → `/login`; alcance no aceptado →
  `/alcance`; admin → solo `/admin*`. Si la ruta es pública, añádela a `isPublic`; si es
  de administrador, empiézala por `/admin`.
- Botón atrás: `SmartBackButton()` o `popOrPanel(context)` de
  [navigation.dart](../../../lib/core/utils/navigation.dart), que nunca deja al usuario
  sin salida.

## 5. Estilo visual

- Colores **solo** desde `AppColors` ([app_colors.dart](../../../lib/core/theme/app_colors.dart)),
  tokens tomados del mockup `Dermavia-mockups-standalone.html`. Semántica:
  `primary*`/`success*` = acción o validado; `warning*` = pendiente o incertidumbre;
  `error*` = riesgo alto o error.
- Identificadores (HC, CASO-XXXX, fechas técnicas) con `AppFonts.mono(...)`.
- Fechas y duraciones con `Fmt` ([formatters.dart](../../../lib/core/utils/formatters.dart)):
  `Fmt.dateTime`, `Fmt.duration`, `Fmt.countdown`, `Fmt.percent`.
- Antes de crear un widget, revisa [common.dart](../../../lib/core/widgets/common.dart):
  `PrimaryButton`, `SecondaryButton`, `AppTextField`, `FieldLabel`, `StepProgress`,
  `InfoBanner(tone: BannerTone.x)`, `StatusChip(tone: ChipTone.x)`, `AppCard`,
  `LesionThumbnail`, `SegmentedSelector`, `PillChip`, `KeyValueRow`, `CheckLine`,
  `SectionLabel`, `LoadingView`, `ErrorView`, `showAppSnack`.
- Pantallas del especialista que dependen de red muestran `OfflineBanner` (de
  `dashboard/case_widgets.dart`) arriba.
- Padding habitual de listas: `EdgeInsets.fromLTRB(18, 14, 18, 24)`; título de pestaña
  22 px w700; texto de apoyo 14 px `textMuted` con `height: 1.45`.

## 6. Textos

- Todo en español neutro peruano, en segunda persona ("Registra…", "Tu sesión…").
- Nunca jerga de ML en textos de predicción (ver [`dermavia-reglas-clinicas`](../dermavia-reglas-clinicas/SKILL.md), §5).
- Usa `.label` de los enums (`CaseStatus.label`, `Symptom.label`, …) en lugar de
  escribir el texto en la pantalla.

## 7. Verificar

```bash
flutter analyze
flutter test
```

Para pantallas con lógica relevante, añade una prueba de widget (ver skill
[`dermavia-pruebas`](../dermavia-pruebas/SKILL.md)). Si puedes, prueba el flujo en el emulador con las cuentas de
demostración del README.
