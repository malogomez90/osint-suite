# Iniciativa: cola acordada (instalación, codex, Telegram público)

Este archivo guía al **SYSTEM ORCHESTRATOR** para montar lo acordado sin reabrir decisiones ya tomadas. Cárgalo antes de ejecutar ítems de **Next Queue** en `codex/status.md`.

## Cómo usarlo (agente y humanos)

1. **Orden de lectura:** en cualquier tarea de **siguiente cola** (`codex/status.md`), **roadmap**, **empaquetado / instalación**, o **implementación del bot de Telegram**, el agente debe leer **primero** `codex/initiative_next.md` y `codex/status.md`, luego el resto del contexto del repo. Esa regla está reflejada en **`.cursorrules`** (bloque “When executing Next Queue / roadmap / …”).
2. **Para qué sirve:** evita que el orquestador **mezcle “frontend web” con el bot**, que **salte la Fase A** (verificación de instalación) antes del Telegram público, o que reabra decisiones ya fijadas en las secciones siguientes.
3. **Carga opcional en todas las sesiones:** si quieres que la iniciativa sea obligatoria **siempre** (no solo en trabajo de cola/bot), puedes mover `codex/initiative_next.md` a la lista **Always load** de `.cursorrules`. **Trade-off:** más contexto en cada conversación (más tokens); la configuración actual lo **acota** a tareas relevantes para no inflar cada chat.
4. **Plantillas de chat versionadas:** instrucciones repetibles para el agente (commit, Fase B, diseño/implementación Telegram, “siguiente ítem”) están en **`codex/session_prompts.md`**. Así no dependes solo de pegar texto en el chat; el repo conserva el texto de referencia.

## Decisiones ya tomadas (no renegociar sin el usuario)

1. **Interfaz de producto cercana:** bot de **Telegram**, **público** (no SPA ni “frontend real” hasta un diseño/alcance explícito aparte).
2. **`codex/`:** modelo **híbrido** — documentación viva para el agente + **contratos** donde hay tests (p. ej. frases mínimas en ciertos `.md`). No duplicar un workflow pesado solo por ser Markdown; el formalismo = **tests + `.cursorrules` + texto breve de contribución**.
3. **Backend:** el repo sigue siendo **Python + CLI + orquestación**; el bot será una **capa nueva** que llama al núcleo, no una sustitución del paquete.

## Fase A — Verificación de instalación y empaquetado (prioridad alta)

**Propietario:** `infra` + `backend` (tests y paquete).

**Objetivo:** ampliar la verificación **más allá de** `setup.py --name` sin romper los smoke tests existentes.

**Checklist de implementación (orden sugerido):**

1. Test: **`import osint_suite`** (y si aplica imports de submódulos críticos) en el entorno de CI/local tras instalar en modo editable.
2. Test: **entry points** registrados — comprobar vía `importlib.metadata.entry_points` (grupo `console_scripts`) que coinciden con lo definido en `setup.py`.
3. Test: **versión** — `importlib.metadata.version("osint-suite")` alineada con la versión en `setup.py` (un solo sitio de verdad o test que compare ambos).
4. Test: **alineación** `requirements.txt` ↔ `install_requires` de `setup.py` (parseo simple; fallar si hay desajuste grave).
5. Opcional posterior: matriz de **versiones de Python** en CI (p. ej. 3.10 y 3.12).

**No reclamar éxito** sin `pytest` verde y sin actualizar `codex/quality_gates.md` si allí listas comprobaciones obligatorias.

## Fase B — Rol de `codex/` y contribución

**Propietario:** `agents` (docs de orquestación) + una mención mínima en documentación raíz si existe `CONTRIBUTING` o `README`.

**Objetivo:** que quede explícito que `codex/` **no** es carpeta informal: gobierna al agente; los archivos con **frases obligatorias** están acoplados a `tests/test_setup.py`.

**Checklist:**

1. Añadir un párrafo corto (README o CONTRIBUTING): cambiar frases contractuales en `codex/*.md` implica **actualizar tests** correspondientes.
2. No mover `codex/` a otra ruta sin actualizar `.cursorrules` y tests que referencian rutas.

## Fase C — Bot de Telegram (público)

**Propietario:** `backend` (código del bot y adaptadores) + `infra` (secretos, despliegue); `agents` solo si hay prompts dedicados.

**Prerrequisitos:** Fase A estable (imports/entry points confiables en CI).

**Alcance mínimo viable (para diseño/implementation plan):**

- Handlers delgados → llamadas al **núcleo** `osint_suite` (sin lógica OSINT en el bot).
- **Tareas largas:** cola o background (evitar timeouts de Telegram); mensaje de “procesando…” donde aplique.
- **Resultados:** texto acotado; JSON grande como **archivo** o troceado.
- **Seguridad pública:** token solo en entorno; **rate limiting** por `user_id`; considerar **lista de permitidos** o moderación si el usuario lo pide después; logs sin datos sensibles por defecto.
- Dependencia explícita (p. ej. `python-telegram-bot` o `aiogram`) en `requirements.txt` / empaquetado cuando exista el código.

**Fuera de alcance hasta nuevo diseño:** panel web, API REST pública amplia, “frontend real” separado.

## Orden de ejecución recomendado para el orquestador

1. Completar **Fase A** con tests nuevos y verificación local/CI.
2. **Fase B** (documentación breve).
3. **Fase C** solo tras escribir/ajustar **plan de implementación** del bot (comandos, límites, manejo de errores) y aprobación del usuario si el protocolo del repo lo exige.

## Coordinación con módulos

| Fase | backend | infra | agents |
|------|---------|-------|--------|
| A | paquete, imports, tests | CI/instalación | — |
| B | — | — | codex + README |
| C | bot + integración OSINT | deploy, secretos | opcional prompts |

Al clasificar tareas: si el usuario pide “solo Telegram”, enrutar a Fase C **sin** asumir frontend web. Si pide “web + API”, detener y pedir **diseño/alcance** explícito primero.
