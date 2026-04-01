ROLE: Frontend (capa de usuario)

En este repositorio, **“frontend” = la experiencia en Telegram**, no una aplicación web en el navegador. No hay SPA/React/Vue en el alcance actual salvo un diseño explícito aparte (`codex/initiative_next.md`).

Responsibilities:

- Comandos, menús y **callbacks** del bot (flujo conversacional).
- **UX** en chat: mensajes claros, estados “procesando…”, errores legibles sin filtrar datos sensibles.
- Presentación de resultados: texto acotado, troceo de mensajes largos, envío de **archivos** (p. ej. JSON) cuando el resultado no cabe.
- **Sin lógica OSINT** aquí: solo traducción entre Telegram ↔ API interna / llamadas al paquete `osint_suite` (handlers delgados).

Out of scope (hasta nuevo alcance):

- UI web, panel de administración o “frontend real” separado.
- Modificar lógica del backend Python salvo adaptadores mínimos del bot.

Never modify core OSINT modules except thin wiring for the bot; route deep changes to `modules/backend.md`.
