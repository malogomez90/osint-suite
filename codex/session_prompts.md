# Plantillas de instrucción (sesiones con el agente)

Este archivo **no** sustituye a `codex/status.md` ni a `codex/initiative_next.md`: define **qué pedir** en el chat cuando quieras una tarea acotada. Convive con el repo (versionado, revisable) en lugar de depender solo de mensajes sueltos.

**Uso:** en un chat nuevo, carga `@codex/status.md` y `@codex/initiative_next.md`, elige **una** plantilla abajo y pégala. No mezcles varias en el mismo mensaje si buscas un solo entregable.

---

## 1 — Commit solo de tests

```
Haz commit solo de tests/ (test_setup.py, conftest.py y lo que corresponda) con un mensaje convencional claro (test/packaging). No toques otros archivos del árbol. Si hay conflicto con cambios ajenos, para y dime qué archivos están en juego.
```

---

## 2 — Fase B: nota para contribuidores

```
Fase B del initiative_next: añade un párrafo corto en README.md (o CONTRIBUTING.md si existe) explicando que codex/ gobierna al agente, que algunos .md son contrato y que cambiar frases obligatorias implica actualizar tests/test_setup.py. No implementes el bot. Cambios mínimos.
```

---

## 3 — Fase C: diseño Telegram (sin código)

```
Diseña la Fase C Telegram en un único doc nuevo bajo codex/ (nombre acordado): alcance MVP, comandos iniciales, rate limiting público, secretos, despliegue, jobs largos vs mensajes, manejo de errores. Sin implementar el bot todavía. Alinea con modules/frontend.md y modules/backend.md.
```

---

## 4 — Fase C: implementar el bot (tras diseño aprobado)

```
Implementa el bot de Telegram según codex/<doc de diseño>.py: handlers finos, llamadas a osint_suite, sin lógica OSINT en handlers. Infra: token por entorno. Incluye dependencia en requirements y prueba manual documentada. No añadas SPA ni API REST pública.
```

---

## 5 — Siguiente ítem de la cola (alcance mínimo)

```
Lee codex/status.md (Last progress y Next Queue) y codex/initiative_next.md. Ejecuta el siguiente ítem de Next Queue con el alcance mínimo; no refactors ni mejoras colaterales.
```
