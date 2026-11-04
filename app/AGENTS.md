# AGENTS.md · Dermavía

Instrucciones para agentes de código (Claude Code, Codex, Cursor, Copilot, Gemini, …).
La descripción funcional del proyecto, las cuentas de demostración y la arquitectura
están en [README.md](README.md).

## Proyecto

App Android en Flutter 3.35 / Dart 3.9 (Riverpod 3 + go_router) de apoyo diagnóstico
para melanoma maligno. Funciona con un backend simulado en memoria (`lib/data/mock/`)
que aplica las mismas reglas de negocio que el backend real. Código, textos de UI,
pruebas y documentación en español.

## Comandos

```bash
flutter pub get
flutter analyze
flutter test
flutter build apk      # solo si cambió android/, pubspec o algo nativo
```

Antes de dar por terminado un cambio, `flutter analyze` y `flutter test` deben pasar.
Informa el resultado real de ambos.

## Skills

Guías del proyecto en [.agents/skills/](.agents/skills/), en formato `SKILL.md`
(frontmatter `name` + `description` y cuerpo en Markdown). **Antes de empezar una tarea,
lee la skill que corresponda y síguela.**

| Skill | Léela cuando… |
|---|---|
| [dermavia-reglas-clinicas](.agents/skills/dermavia-reglas-clinicas/SKILL.md) | vayas a tocar `lib/domain`, `lib/data/mock`, los repositorios o cualquier pantalla que muestre casos, predicciones, validaciones o informes. Reglas que ningún cambio puede romper. |
| [dermavia-nueva-pantalla](.agents/skills/dermavia-nueva-pantalla/SKILL.md) | añadas o modifiques una pantalla, ruta o acción de UI en `lib/features`. |
| [dermavia-repositorios](.agents/skills/dermavia-repositorios/SKILL.md) | añadas o cambies una operación de datos, toques `MockBackend`/`seed_data` o integres el backend real. |
| [dermavia-pruebas](.agents/skills/dermavia-pruebas/SKILL.md) | escribas pruebas o vayas a verificar un cambio. |

## Reglas mínimas (detalle en las skills)

- La app **no clasifica** lesiones; toda predicción es preliminar y requiere validación
  del especialista. Ningún cambio puede saltarse el flujo
  `REGISTRADO → EN_ANALISIS → PENDIENTE_VALIDACION → VALIDADO → CERRADO`.
- Las reglas de negocio viven en la capa de datos, no solo en la UI.
- Sin jerga de ML en textos visibles ("umbral", "probabilidad calibrada", "modelo", …).
- Las pantallas leen datos solo a través de los providers de `lib/providers/`.

## Mantener las skills

- El contenido de cada skill vive **solo** en `.agents/skills/<nombre>/SKILL.md`.
- `.claude/skills/<nombre>/SKILL.md` es un stub para que Claude Code descubra la skill;
  si cambias `name` o `description`, actualiza también el stub y la tabla de arriba.
