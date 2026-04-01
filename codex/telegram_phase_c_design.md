# Fase C - Diseño del bot de Telegram (MVP)

## Estado y objetivo

Este documento define el alcance mínimo del bot público de Telegram para `osint-suite` sin introducir SPA, panel web ni API REST pública. El bot es una capa de interacción y orquestación: la lógica OSINT permanece en `osint_suite`, y los handlers de Telegram solo validan la entrada, aplican políticas básicas y delegan al backend.

## Alineación por módulo

- `modules/frontend.md`: la experiencia de usuario es Telegram. El bot debe responder con mensajes claros, estados de "procesando...", troceo de respuestas largas y archivos adjuntos cuando el resultado no quepa en chat.
- `modules/backend.md`: el bot pertenece al backend, con handlers finos y sin lógica OSINT incrustada. La ejecución real debe invocar funciones reutilizables del paquete `osint_suite`.
- `modules/infra.md`: secretos y despliegue del proceso del bot viven en infraestructura, no en el código del handler.

## Alcance MVP

- Exponer un bot público de Telegram con un conjunto pequeño de comandos de entrada.
- Delegar cada comando a funciones ya existentes de `osint_suite` o a adaptadores ligeros sobre esas funciones.
- Soportar resultados cortos en texto y resultados grandes como archivo JSON.
- Responder de forma segura cuando una operación tarde demasiado o falle.
- Aplicar rate limiting por `user_id`.

Fuera de alcance en esta fase:

- SPA, panel web, API REST para terceros.
- Flujos conversacionales complejos con múltiples pasos persistidos.
- Base de datos dedicada, colas distribuidas o infraestructura pesada si no son estrictamente necesarias para el MVP.

## Comandos iniciales propuestos

- `/start`: presenta propósito, límites del bot y comandos disponibles.
- `/help`: ayuda breve y ejemplos de uso.
- `/username <valor>`: ejecuta búsqueda de username.
- `/email <valor>`: ejecuta análisis de email.
- `/phone <valor>`: ejecuta investigación de teléfono.
- `/company <valor>`: ejecuta investigación de empresa.
- `/geo <lat,lon>`: ejecuta ayuda de geolocalización.

Comandos diferidos para una iteración posterior:

- `/document`, `/image` y otros flujos que requieran subida de archivos o parsing más costoso.
- Comandos administrativos.

## Arquitectura propuesta

La opción recomendada para el MVP es un proceso único del bot con handlers asíncronos y una capa de servicios interna:

1. Handler de Telegram recibe update y normaliza la petición.
2. Middleware ligero aplica rate limiting, trazas mínimas y validación básica.
3. Servicio de aplicación traduce el comando a una llamada concreta del paquete `osint_suite`.
4. El servicio devuelve un resultado estructurado.
5. Un adaptador de presentación decide si responde con texto corto, mensaje troceado o archivo JSON.

Esta opción minimiza superficie nueva, mantiene la lógica en el backend existente y deja abierta una futura extracción de jobs/cola si los tiempos reales lo exigen.

## Jobs largos frente a mensajes inmediatos

Regla operativa del MVP:

- Si una operación es corta, el bot responde en la misma ejecución del handler.
- Si una operación supera un umbral configurable de latencia, el bot envía primero un mensaje de "procesando..." y ejecuta el trabajo en background dentro del mismo proceso.
- Si el resultado final es demasiado largo para chat, se envía un resumen breve y un archivo `.json`.

Diseño recomendado para trabajos largos:

- Usar `asyncio.create_task` o mecanismo equivalente en el proceso del bot para no bloquear la respuesta inicial.
- Mantener un número pequeño y controlado de trabajos concurrentes por usuario.
- No introducir una cola externa en el MVP salvo que las pruebas manuales muestren timeouts o saturación real.

## Rate limiting público

Política inicial recomendada:

- Límite por `user_id` con ventana corta para ráfagas y ventana media para abuso.
- Ejemplo operativo inicial: 1 job largo concurrente por usuario, 5 comandos por minuto y 20 comandos por hora.
- Respuesta explícita cuando se excede el límite, sin exponer detalles internos.

La implementación debe ser simple y en memoria para el MVP. Si el despliegue futuro requiere múltiples réplicas, esa política podrá migrarse a un backend compartido.

## Secretos y configuración

Variables mínimas de entorno:

- `TELEGRAM_BOT_TOKEN`: obligatorio.
- `TELEGRAM_ALLOWED_USERS`: opcional para modo restringido.
- `TELEGRAM_RATE_LIMIT_PER_MINUTE`: opcional.
- `TELEGRAM_RATE_LIMIT_PER_HOUR`: opcional.
- `TELEGRAM_LONG_JOB_THRESHOLD_SECONDS`: opcional.

Reglas:

- Nunca hardcodear el token.
- No registrar el token ni payloads completos sensibles.
- Documentar un ejemplo de configuración local y de despliegue sin incluir secretos reales.

## Despliegue

Despliegue MVP recomendado:

- Un proceso Python dedicado al bot, separado del uso CLI.
- Configuración por variables de entorno.
- Modo polling para simplificar el arranque inicial.

Webhook queda fuera del MVP porque añade complejidad operativa innecesaria para la primera entrega pública. Si el volumen de tráfico crece, se podrá reevaluar.

## Manejo de resultados

- Respuesta textual breve para éxito simple.
- Resumen + archivo JSON cuando el resultado sea largo o estructurado.
- Mensajes de error legibles para el usuario y logs técnicos mínimos para operación.
- No mostrar stack traces, rutas locales ni datos sensibles en el chat.

## Manejo de errores

Categorías:

- Error de entrada: comando incompleto o parámetro inválido. Respuesta inmediata con ejemplo correcto.
- Error de operación controlada: fallo esperado de una herramienta o dependencia. Respuesta corta y reintento manual por parte del usuario.
- Error interno inesperado: mensaje genérico al usuario y log técnico sanitizado.
- Error de saturación o rate limit: mensaje claro de espera.

## Dependencias e integración

La dependencia del framework de Telegram debe declararse explícitamente en `requirements.txt` y en el empaquetado del proyecto cuando se implemente el código. La integración debe introducir una pequeña capa de servicios del bot para adaptar llamadas a `osint_suite` sin mover lógica de negocio a los handlers.

## Verificación manual prevista

Antes de declarar la implementación como correcta:

- Arranque local del bot con token por entorno.
- Prueba de `/start` y `/help`.
- Prueba de al menos dos comandos reales sobre herramientas existentes.
- Verificación de rate limiting por usuario.
- Verificación de un caso de job largo con mensaje de "procesando...".
- Verificación de envío de archivo JSON cuando el resultado exceda el tamaño razonable del chat.

## Recomendación final

La recomendación es implementar primero un MVP con polling, handlers finos, servicios internos reutilizables y rate limiting en memoria. Esto mantiene el alcance pequeño, respeta la separación frontend/backend del repo y evita introducir infraestructura prematura.
