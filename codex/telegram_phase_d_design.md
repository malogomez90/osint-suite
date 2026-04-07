# Fase D - Userbot Avanzado: Recon, Grafo y Correlación

## Estado y objetivo

Esta fase extiende el userbot MTProto con capacidades avanzadas de recon, mapeo de redes, búsqueda global y correlación cruzada. El objetivo es transformar el bot de una herramienta de lookup individual en una plataforma de investigación OSINT completa sobre Telegram.

**Principios:**
- Read-only: cero operaciones de escritura.
- Anti-ban: mantener delays, rate limiting, flood wait y rotación de sesiones.
- Paridad de contrato: todo devuelve `CommandResult` con `summary` + `payload` + `filename_prefix`.
- Graceful degradation: si una API falla, devolver lo disponible sin romper el flujo.

## Comandos nuevos

### 1. `/tgphone <numero>`
**Propósito:** Resolver un número de teléfono en una identidad de Telegram.

**Flujo:**
1. Normalizar número (añadir `+` si falta, validar formato).
2. `contacts.importContacts([InputPhoneContact(...)])` con contacto temporal.
3. Si Telegram devuelve `User` → extraer perfil completo (igual que `/tginfo`).
4. `contacts.deleteContacts(id=[...])` inmediatamente para limpiar.
5. Si no encontrado → `"El número +XX no está registrado en Telegram."`

**APIs Telethon:**
- `client(functions.contacts.ImportContactsRequest(contacts=[...]))`
- `client(functions.contacts.DeleteContactsRequest(id=[...]))`
- `client.get_entity(user_id)` → perfil completo

**Riesgo:** Medio. Importar contactos es escritura, pero se borra inmediatamente. Limitar a 1 consulta por minuto.

**Output:**
```
Resolución Telegram +34612345678
- ID: 123456789
- Nombre: Juan Pérez
- Username: @juanperez
- Bio: ...
- Teléfono: +34612345678
- Estado: UserStatusRecently
- Flags: premium, verificado
```

---

### 2. `/tgmembers <grupo> [--limit N]`
**Propósito:** Extraer miembros de un grupo donde el userbot sea miembro.

**Flujo:**
1. `client.get_entity(grupo)` → resolver canal/grupo.
2. `client(functions.channels.GetParticipantsRequest(channel, filter=ChannelParticipantsRecent, offset=0, limit=N))`
3. Por cada participante: `id`, `username`, `first_name`, `last_name`, `phone` (si visible), `status`.
4. Paginar con delay anti-ban entre batches (máx 200 por defecto).
5. Devolver resumen + JSON con lista completa.

**APIs Telethon:**
- `GetParticipantsRequest` con `ChannelParticipantsRecent`, `ChannelParticipantsAdmins`, `ChannelParticipantsSearch`
- Paginación con `offset` + `limit` (max 200 por llamada)

**Riesgo:** Medio-Alto. Grupos grandes = muchas llamadas. Limitar a 200 por defecto, max 1000 con `--limit`. Delay de 2-5s entre batches.

**Output:**
```
Miembros de @grupo_secreto
- Total extraídos: 150/500
- Con username público: 89
- Admins: 5
- Bots: 3
- Usuarios premium: 42
Archivo JSON adjunto con perfiles completos.
```

---

### 3. `/tgsearch <query> [--chat @canal] [--from @user] [--limit N]`
**Propósito:** Buscar un término en mensajes accesibles del userbot.

**Flujo:**
1. Si `--chat @canal`: buscar solo en ese canal/grupo.
2. Si `--from @user`: buscar solo mensajes de ese usuario (requiere chat).
3. Si sin filtros: búsqueda global en todos los chats del userbot.
4. `client(functions.messages.SearchRequest(...))` o `SearchGlobalRequest`.
5. Por cada resultado: `chat_title`, `from_user`, `date`, `message_text`, `views`, `forwards`.
6. Limitar a 20 por defecto, max 100.

**APIs Telethon:**
- `SearchRequest(peer, q, filter, min_date, max_date, offset_id, add_offset, limit, max_id, min_id, hash)`
- `SearchGlobalRequest(q, offset_rate, offset_peer, offset_id, add_offset, limit, folder_id)`
- Filtros: `InputMessagesFilterEmpty`, `InputMessagesFilterPhotos`, `InputMessagesFilterDocument`, etc.

**Riesgo:** Medio. Búsqueda global = muchas llamadas. Delay entre paginación.

**Output:**
```
Búsqueda: "bitcoin" en todos los chats
- Resultados: 15 mensajes en 4 chats
- @crypto_es: 8 menciones
- @inversiones: 4 menciones
- Chat privado: 3 menciones
Archivo JSON adjunto con mensajes completos.
```

---

### 4. `/tggraph <username> --depth 2`
**Propósito:** Construir un grafo de conexiones del target.

**Flujo:**
1. Seed: `client.get_entity(username)` → user_id.
2. `GetCommonChatsRequest(user_id)` → lista de grupos compartidos.
3. Para cada grupo (depth=1): `GetParticipantsRequest` → miembros.
4. Para cada miembro (depth=2): extraer `id`, `username`, `first_name`.
5. Construir grafo: `{nodes: [...], edges: [...]}`.
6. Output: JSON en formato GraphML + resumen.

**APIs Telethon:**
- `GetCommonChatsRequest`
- `GetParticipantsRequest` por grupo
- Anti-ban entre cada llamada

**Riesgo:** Alto. Exponencial con depth. Limitar depth=1 (default) o depth=2 (max). Max 50 miembros por grupo.

**Output:**
```
Grafo de conexiones de @target
- Grupos comunes: 7
- Nodos únicos: 342
- Usuarios con username público: 198
- Admins en grupos compartidos: 12
Archivo GraphML adjunto para visualizar en Gephi.
```

---

### 5. `/tgsessions`
**Propósito:** Auditoría de seguridad de sesiones activas.

**Flujo:**
1. `client(functions.account.GetAuthorizationsRequest())` → lista de `Authorization`.
2. Por cada sesión: `app_name`, `device_model`, `platform`, `system_version`, `ip`, `country`, `date_created`, `date_active`, `official`, `password_pending`, `encrypted_requests_disabled`.
3. Marcar cuál es la sesión actual.
4. Output: resumen en chat + JSON detallado.

**APIs Telethon:**
- `GetAuthorizationsRequest` — una sola llamada, bajo riesgo.

**Riesgo:** Bajo. Solo lectura de metadatos de sesiones.

**Output:**
```
Sesiones activas de la cuenta userbot
- Total: 3 sesiones
- Sesión actual: Linux Desktop - Telegram Desktop 4.8.1 (activa ahora)
- Sesión 2: iPhone 14 - iOS 16.3 (última vez: 2026-04-07)
- Sesión 3: Chrome - macOS (última vez: 2026-04-01) ⚠️ sospechosa
```

---

### 6. `/tgcorrelate <username>`
**Propósito:** Encontrar menciones del username en canales/grupos públicos y detectar URLs de otras plataformas.

**Flujo:**
1. Búsqueda global: `SearchGlobalRequest(q=username)`.
2. Por cada resultado: extraer texto del mensaje.
3. Regex para detectar URLs de plataformas:
   - Twitter/X: `twitter.com/`, `x.com/`
   - Instagram: `instagram.com/`
   - OnlyFans: `onlyfans.com/`
   - TikTok: `tiktok.com/`
   - YouTube: `youtube.com/`, `youtu.be/`
   - GitHub: `github.com/`
   - LinkedIn: `linkedin.com/in/`
   - Telegram: `t.me/`
4. Correlacionar: `"@usuario mencionado en @canal_crypto con link a twitter.com/@usuario"`.
5. Output: resumen + JSON con menciones y plataformas detectadas.

**APIs Telethon:**
- `SearchGlobalRequest`
- Regex sobre texto de mensajes

**Riesgo:** Medio. Búsqueda global = múltiples llamadas. Delay entre paginación.

**Output:**
```
Correlación de @target
- Menciones encontradas: 23 en 8 chats
- Plataformas detectadas:
  - Twitter/X: @target (5 menciones)
  - Instagram: target_user (3 menciones)
  - OnlyFans: target_of (2 menciones)
  - GitHub: target-dev (1 mención)
Archivo JSON adjunto con todas las menciones.
```

---

### 7. `/tgforwardchain <message_link>`
**Propósito:** Trazar la cadena completa de forwards de un mensaje.

**Flujo:**
1. Parsear link: `https://t.me/channel/1234` → `channel`, `msg_id`.
2. `client.get_messages(channel, ids=msg_id)` → obtener `Message`.
3. Analizar `message.fwd_from`:
   - `from_id` → canal/usuario origen
   - `channel_post` → ID del mensaje original
   - `date` → fecha del forward
   - `saved_from_peer` → si viene de saved messages
4. Si el forward viene de un canal → buscar el mensaje original en ese canal → repetir.
5. Construir cadena: `[origen] → [forward 1] → [forward 2] → ... → [tú]`.
6. Si `noforwards` activo → cadena se rompe ahí.
7. Output: cadena visual + JSON.

**APIs Telethon:**
- `get_messages(channel, ids=[...])`
- `fwd_from` field del `Message` object
- Iterativo hasta que no haya más `fwd_from` o se encuentre `noforwards`

**Riesgo:** Bajo. Solo lectura de mensajes específicos. Max depth 10 para evitar loops.

**Output:**
```
Cadena de forwards (4 hops):
1. @canal_origen (post #5678) - 2026-04-01 12:00 UTC
   → "Texto original del mensaje..."
2. @canal_intermedio (post #9012) - 2026-04-03 15:30 UTC
3. @otro_canal (post #3456) - 2026-04-05 09:15 UTC
4. Mensaje reenviado a ti - 2026-04-07 20:00 UTC
Fuente original: @canal_origen
```

---

## Diseño de implementación

### Nuevos archivos

- `osint_suite/telegram_advanced.py` — Pool de userbot avanzado con los 7 comandos.
- `tests/test_telegram_advanced.py` — Tests unitarios con mocks.

### Cambios en archivos existentes

- `osint_suite/telegram_bot.py` — Registrar 7 nuevos comandos + handlers.
- `osint_suite/telegram_services.py` — Nuevos dispatchers si es necesario.
- `tests/test_telegram_bot.py` — Tests de integración para nuevos comandos.

### Patrón de implementación

Cada comando sigue el mismo patrón que `/tginfo` y `/tggroupinfo`:

1. Handler en `telegram_bot.py` → valida entrada, rate limit, job slot.
2. Llama a método en `TelegramOSINTPool` o nueva clase `TelegramAdvancedPool`.
3. Método ejecuta consulta(s) MTProto con anti-ban.
4. Devuelve `Dict[str, Any]` estructurado.
5. Handler construye `CommandResult` con `summary` + `payload`.
6. `send_command_result()` envía resumen o JSON según tamaño.

### Anti-ban para operaciones pesadas

Para comandos que hacen múltiples llamadas (`/tgmembers`, `/tggraph`, `/tgsearch`, `/tgcorrelate`):

- Delay entre batches: `random.uniform(2.0, 6.0)` segundos (más que el 1-4s de lookups simples).
- Max items por defecto: 200 para members, 20 para search.
- Progreso: enviar mensaje de `"Procesando 50/200..."` cada 50 items.
- Timeout: 60s máximo por comando (configurable con `TELEGRAM_ADVANCED_ANALYSIS_TIMEOUT`).

### Variables de entorno nuevas

- `TELEGRAM_ADVANCED_ANALYSIS_TIMEOUT` — Timeout para comandos avanzados (default: 60s).
- `TELEGRAM_MEMBERS_MAX_LIMIT` — Límite máximo para `/tgmembers` (default: 200, max: 1000).
- `TELEGRAM_GRAPH_MAX_DEPTH` — Profundidad máxima para `/tggraph` (default: 1, max: 2).
- `TELEGRAM_SEARCH_GLOBAL_LIMIT` — Límite para búsqueda global (default: 20, max: 100).

---

## Tests

### Cobertura requerida

Para cada comando:
1. Caso feliz con datos mock.
2. Error por userbot no configurado.
3. Error por argumento vacío/inválido.
4. Error por entidad no encontrada.
5. Error por flood limit / session unavailable.
6. Error por permiso insuficiente (no miembro del grupo).
7. Rate limiting del bot.

### Tests específicos

- `/tgphone`: número válido encontrado, número no registrado, formato inválido.
- `/tgmembers`: grupo público, grupo privado (sin acceso), grupo vacío.
- `/tgsearch`: búsqueda global, búsqueda por chat, sin resultados.
- `/tggraph`: depth=1, depth=2, sin grupos comunes.
- `/tgsessions`: 1 sesión, múltiples sesiones, error de auth.
- `/tgcorrelate`: con menciones, sin menciones, múltiples plataformas.
- `/tgforwardchain`: cadena de 1 hop, cadena de 5 hops, noforwards activo, link inválido.

---

## Prioridad de implementación

| Orden | Comando | Complejidad | Dependencias |
|-------|---------|-------------|--------------|
| 1 | `/tgphone` | Media | Ninguna |
| 2 | `/tgsessions` | Baja | Ninguna |
| 3 | `/tgforwardchain` | Media | Ninguna |
| 4 | `/tgsearch` | Media-Alta | Ninguna |
| 5 | `/tgcorrelate` | Alta | Depende de `/tgsearch` |
| 6 | `/tgmembers` | Media-Alta | Ninguna |
| 7 | `/tggraph` | Muy Alta | Depende de `/tgmembers` |

---

## Supuestos y límites

- `/tgphone` importa y borra contactos inmediatamente. Si el target tiene "¿Quién puede encontrarme por mi número?" = "Nadie", no funcionará.
- `/tgmembers` solo funciona en grupos donde el userbot es miembro. No se puede extraer de grupos privados donde no se está.
- `/tggraph` con depth=2 en grupos grandes puede generar miles de nodos. Se limita a 50 miembros/grupo y max 10 grupos.
- `/tgcorrelate` solo encuentra menciones indexadas por Telegram. No busca en la web externa.
- `/tgforwardchain` se rompe si algún canal tiene `noforwards=True`. No hay workaround.
- Todos los comandos son read-only excepto `/tgphone` (import+delete contact).
