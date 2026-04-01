ROLE: Backend (Python + integración)

El **backend** de este repo es el **código Python ejecutable**: paquete `osint_suite`, CLIs, y **integración del bot de Telegram** (handlers, servicios, colas). No hay API REST pública amplia en el alcance actual salvo diseño explícito (`codex/initiative_next.md`).

Qué incluye:

- **`osint_suite/`:** herramientas OSINT, validación de entradas de dominio, salidas serializables (dict/JSON); **toda la lógica OSINT vive aquí** o en módulos que este paquete invoca.
- **CLI / entry points:** `setup.py` → `console_scripts`; mantener alineados con tests de humo (`tests/test_setup.py`).
- **Bot de Telegram (cuando exista):** capa fina — recibe updates, aplica **rate limiting** y políticas por `user_id`, delega en funciones del paquete; **tareas largas** vía async/col/worker según diseño; errores técnicos sin filtrar datos sensibles en logs.
- **Servicios de aplicación:** funciones que orquestan una o varias herramientas del paquete para un caso de uso (p. ej. un comando del bot), sin duplicar lógica OSINT en el handler.

Qué no incluye (otros módulos):

- **Secretos y despliegue** del proceso del bot → `modules/infra.md`.
- **Textos de UX, flujo conversacional y reglas de presentación en el chat** → coordinar con `modules/frontend.md` (el backend implementa; el “qué dice” el usuario puede acordarse en frontend).

Fuera de alcance hasta nuevo alcance:

- Servidor HTTP “público” tipo REST/GraphQL para terceros; panel web; base de datos compleja salvo que el diseño lo pida.

Never modify `modules/frontend.md` salvo coordinación explícita. No empujar lógica OSINT pesada fuera de `osint_suite` hacia handlers del bot sin extraerla a funciones reutilizables en el paquete.
