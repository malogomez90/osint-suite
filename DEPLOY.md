# Guía de Despliegue - OSINT Suite

Documentación completa para instalar y desplegar la suite de herramientas OSINT en diferentes entornos.

## 📋 Requisitos del Sistema

- **Python**: 3.8 o superior
- **Sistema Operativo**: Windows, Linux, macOS
- **Espacio en disco**: ~50 MB
- **Memoria RAM**: 512 MB mínimo
- **Conexión a Internet**: Requerida para algunas herramientas (búsquedas online)

## 🚀 Opciones de Despliegue

### Opción 1: Instalación Local (Desarrollo)

```bash
# 1. Clonar o navegar al repositorio
cd osint-suite

# 2. Crear entorno virtual (recomendado)
python -m venv venv

# Activar entorno virtual:
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 3b. Dependencias de desarrollo opcionales
pip install -r requirements-dev.txt

# 4. Verificar instalación
python -m osint_suite.main --help
```

### Opción 2: Instalación como Paquete Python

```bash
# 1. Navegar al directorio
cd osint-suite

# 2. Instalar en modo editable (desarrollo)
pip install -e .

# 3. Instalar permanentemente
pip install .

# 4. Usar desde cualquier lugar
osint-suite --menu
```

### Opción 3: Despliegue con Docker

Crear `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar archivos
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Instalar el paquete
RUN pip install .

# Punto de entrada
ENTRYPOINT ["osint-suite"]
CMD ["--menu"]
```

Construir y ejecutar:

```bash
# Construir imagen
docker build -t osint-suite .

# Ejecutar interactivo
docker run -it osint-suite

# Ejecutar herramienta específica
docker run -it osint-suite username-search -u johndoe
```

### Opción 4: Instalación en Servidor (Producción)

#### Linux (systemd service)

Crear archivo `/etc/systemd/system/osint-suite.service`:

```ini
[Unit]
Description=OSINT Suite Service
After=network.target

[Service]
Type=simple
User=osint
WorkingDirectory=/opt/osint-suite
Environment="PATH=/opt/osint-suite/venv/bin"
ExecStart=/opt/osint-suite/venv/bin/python -m osint_suite.main --menu
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Comandos de instalación:

```bash
# 1. Crear usuario
sudo useradd -r -s /bin/false osint

# 2. Copiar archivos
sudo mkdir -p /opt/osint-suite
sudo cp -r * /opt/osint-suite/
sudo chown -R osint:osint /opt/osint-suite

# 3. Crear entorno virtual
cd /opt/osint-suite
sudo -u osint python3 -m venv venv
sudo -u osint venv/bin/pip install -r requirements.txt

# 4. Instalar servicio
sudo cp osint-suite.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable osint-suite
sudo systemctl start osint-suite

# 5. Verificar estado
sudo systemctl status osint-suite
```

## 📦 Dependencias

Las dependencias de runtime se instalan automáticamente con `requirements.txt`:

| Paquete | Versión | Propósito |
|---------|---------|-----------|
| requests | >=2.28.0 | Peticiones HTTP |
| beautifulsoup4 | >=4.11.0 | Parsing HTML |
| lxml | >=4.9.0 | Parser XML/HTML |
| Pillow | >=9.0.0 | Procesamiento de imágenes |
| piexif | >=1.1.3 | Manipulación EXIF |
| pypdf | >=4.2.0 | Análisis de PDF |
| python-docx | >=0.8.11 | Análisis de Word |
| openpyxl | >=3.0.10 | Análisis de Excel |
| olefile | >=0.46 | Análisis de archivos OLE |
| phonenumbers | >=8.13.0 | Validación de teléfonos |
| python-dateutil | >=2.8.2 | Manipulación de fechas |

Dependencias de desarrollo opcionales en `requirements-dev.txt`:

| Paquete | Versión | Propósito |
|---------|---------|-----------|
| pytest | >=7.0.0 | Tests automáticos |
| black | >=22.0.0 | Formateo de código |
| flake8 | >=4.0.0 | Linting |

## 🔧 Configuración

### Variables de Entorno

Crear archivo `.env` en el directorio raíz:

```bash
# Configuración general
OSINT_SUITE_DEBUG=false
OSINT_SUITE_LOG_LEVEL=INFO

# APIs externas (opcional)
HIBP_API_KEY=tu_api_key_aqui
EMAILREP_API_KEY=tu_api_key_aqui

# Telegram bot
TELEGRAM_BOT_TOKEN=tu_bot_token
TELEGRAM_MAX_UPLOAD_SIZE_BYTES=10485760
TELEGRAM_MAX_DOCUMENT_UPLOAD_SIZE_BYTES=10485760
TELEGRAM_MAX_IMAGE_UPLOAD_SIZE_BYTES=5242880
TELEGRAM_ANALYSIS_TIMEOUT_SECONDS=30
TELEGRAM_ALLOWED_DOCUMENT_EXTENSIONS=.pdf,.docx,.xlsx,.pptx,.odt,.ods,.odp,.rtf,.doc,.xls,.ppt
TELEGRAM_ALLOWED_IMAGE_EXTENSIONS=.jpg,.jpeg,.png,.gif,.bmp,.tif,.tiff,.webp
```

### Configuración por Herramienta

#### Username Search
```bash
# Delay entre peticiones (segundos)
export USERNAME_SEARCH_DELAY=1.0

# Workers concurrentes
export USERNAME_SEARCH_WORKERS=5
```

#### Email OSINT
```bash
# Verificar filtraciones automáticamente
export EMAIL_CHECK_BREACH=true
```

## 🧪 Verificación de Instalación

Ejecutar tests de verificación:

```bash
# Verificar Python
python --version

# Verificar dependencias
pip list | grep -E "(requests|beautifulsoup4|Pillow|phonenumbers)"

# Verificar herramientas individuales
python -m osint_suite.username_search --help
python -m osint_suite.email_osint --help
python -m osint_suite.phone_investigator --help

# Ejecutar menú principal
python -m osint_suite.main --menu
```

## 🌐 Despliegue Web (Opcional)

Para exponer vía web, crear API con Flask:

```python
# api.py
from flask import Flask, jsonify, request
from osint_suite.username_search import UsernameSearcher

app = Flask(__name__)

@app.route('/api/username/<username>')
def search_username(username):
    searcher = UsernameSearcher()
    results = searcher.search(username)
    return jsonify(results)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
```

Ejecutar:
```bash
pip install flask
python api.py
```

## Telegram Bot (MVP público)

El frontend actual del proyecto es Telegram, no una SPA. El bot se ejecuta como un proceso Python separado y delega en `osint_suite` para el trabajo OSINT.

Variables de entorno del bot:

```bash
# Obligatoria
export TELEGRAM_BOT_TOKEN="tu_token"

# Opcionales
export TELEGRAM_ALLOWED_USERS="123456789,987654321"
export TELEGRAM_RATE_LIMIT_PER_MINUTE=5
export TELEGRAM_RATE_LIMIT_PER_HOUR=20
export TELEGRAM_LONG_JOB_THRESHOLD_SECONDS=5
export TELEGRAM_MAX_CONCURRENT_JOBS=1
export TELEGRAM_RESULT_FILE_THRESHOLD_BYTES=2500
```

Valores operativos recomendados:

- `TELEGRAM_BOT_TOKEN`: obligatorio. Nunca en código ni en commits.
- `TELEGRAM_ALLOWED_USERS`: vacío para modo público; úsalo si quieres arranque restringido.
- `TELEGRAM_RATE_LIMIT_PER_MINUTE=5`: límite corto por usuario.
- `TELEGRAM_RATE_LIMIT_PER_HOUR=20`: límite sostenido por usuario.
- `TELEGRAM_LONG_JOB_THRESHOLD_SECONDS=5`: a partir de aquí el job ya cuenta como largo en logs.
- `TELEGRAM_MAX_CONCURRENT_JOBS=1`: evita saturación por usuario en el MVP.
- `TELEGRAM_RESULT_FILE_THRESHOLD_BYTES=2500`: payloads grandes salen como JSON adjunto.

Arranque local:

```bash
python -m osint_suite.telegram_bot
```

Validación de configuración antes de arrancar:

```bash
python -m osint_suite.telegram_bot --check-config
```

Despliegue recomendado en producción: polling con `systemd`

Archivo `/etc/systemd/system/osint-telegram-bot.service`:

```ini
[Unit]
Description=OSINT Suite Telegram Bot
After=network.target

[Service]
Type=simple
User=osint
WorkingDirectory=/opt/osint-suite
Environment="PATH=/opt/osint-suite/venv/bin"
Environment="TELEGRAM_BOT_TOKEN=pon_aqui_el_token_o_carga_un_env_file"
Environment="TELEGRAM_RATE_LIMIT_PER_MINUTE=5"
Environment="TELEGRAM_RATE_LIMIT_PER_HOUR=20"
Environment="TELEGRAM_LONG_JOB_THRESHOLD_SECONDS=5"
Environment="TELEGRAM_MAX_CONCURRENT_JOBS=1"
ExecStart=/opt/osint-suite/venv/bin/python -m osint_suite.telegram_bot
Restart=always
RestartSec=5
TimeoutStopSec=20

[Install]
WantedBy=multi-user.target
```

Instalación del servicio:

```bash
sudo systemctl daemon-reload
sudo systemctl enable osint-telegram-bot
sudo systemctl start osint-telegram-bot
sudo systemctl status osint-telegram-bot
```

Verificación manual mínima:

```bash
# 1. Validar configuración sin arrancar polling
python -m osint_suite.telegram_bot --check-config

# 2. Arrancar el bot
python -m osint_suite.telegram_bot

# 3. Probar en Telegram:
# /start
# /help
# /username johndoe
# /email usuario@ejemplo.com
# /phone +34612345678
```

Notas operativas:

- El token solo debe ir en variables de entorno.
- El bot aplica rate limiting por `user_id`.
- Los resultados grandes se envían como JSON adjunto en el chat.
- El patrón recomendado del MVP es `polling`, no webhook.
- Si el proceso cae, `systemd` debe reiniciarlo automáticamente.
- No expongas trazas internas ni payloads sensibles en logs.

## 📊 Monitoreo

### Logs

Los logs se guardan automáticamente en:
- Linux: `/var/log/osint-suite/`
- Windows: `%APPDATA%\osint-suite\logs\`
- macOS: `~/Library/Logs/osint-suite/`

Para el bot en `systemd`, consulta:

```bash
journalctl -u osint-telegram-bot -f
```

Señales mínimas a revisar:

- arranque correcto tras `--check-config`
- reinicios repetidos del servicio
- mensajes de rate limiting excesivo
- errores internos repetidos al ejecutar un mismo comando

### Health Check

```bash
# Script de verificación
python -c "
from osint_suite.utils import print_banner
from osint_suite.username_search import UsernameSearcher
from osint_suite.email_osint import EmailOSINT
print('✓ Todas las importaciones funcionan correctamente')
"
```

## 🔒 Seguridad

### Recomendaciones

1. **No ejecutar como root**: Usar usuario dedicado
2. **Rate limiting**: Configurar delays apropiados
3. **API Keys**: Almacenar en variables de entorno, nunca en código
4. **Logs**: Rotar logs periódicamente
5. **Actualizaciones**: Mantener dependencias actualizadas

```bash
# Actualizar dependencias
pip install --upgrade -r requirements.txt
```

## 🆘 Solución de Problemas

### Problema: ImportError
```bash
# Solución: Reinstalar en modo editable
pip install -e .
```

### Problema: Permisos denegados
```bash
# Linux/macOS
chmod +x -R osint_suite/

# Windows
# Ejecutar como Administrador o verificar permisos de carpeta
```

### Problema: Dependencias faltantes
```bash
# Reinstalar todas las dependencias
pip install --force-reinstall -r requirements.txt
```

### Problema: falta `TELEGRAM_BOT_TOKEN`
```bash
# Síntoma
python -m osint_suite.telegram_bot --check-config
# -> Missing TELEGRAM_BOT_TOKEN

# Solución
export TELEGRAM_BOT_TOKEN="tu_token"
```

### Problema: el bot arranca pero no responde

- Verifica que el token sea correcto y pertenezca al bot esperado.
- Si `TELEGRAM_ALLOWED_USERS` está definido, confirma que tu `user_id` esté en la lista.
- Revisa `journalctl -u osint-telegram-bot -f` para ver reinicios o errores internos.

### Problema: demasiados usuarios golpean el bot

- Reduce `TELEGRAM_MAX_CONCURRENT_JOBS` si el host se satura.
- Baja `TELEGRAM_RATE_LIMIT_PER_MINUTE` o `TELEGRAM_RATE_LIMIT_PER_HOUR`.
- Si el uso crece de verdad, reevaluar cola externa o arquitectura fuera del MVP.

## 📈 Escalado

Para uso intensivo, considerar:

1. **Caché de resultados**: Implementar Redis/Memcached
2. **Cola de tareas**: Usar Celery + RabbitMQ/Redis
3. **Balanceo de carga**: Múltiples instancias con nginx
4. **Base de datos**: PostgreSQL para almacenar resultados históricos

## 📝 Checklist de Despliegue

- [ ] Python 3.8+ instalado
- [ ] Entorno virtual creado
- [ ] Dependencias de runtime instaladas (`pip install -r requirements.txt`)
- [ ] Dependencias de desarrollo instaladas si aplica (`pip install -r requirements-dev.txt`)
- [ ] Herramientas importables (`python -c "from osint_suite import *"`)
- [ ] Menú principal funciona (`python -m osint_suite.main --menu`)
- [ ] Config del bot válida (`python -m osint_suite.telegram_bot --check-config`)
- [ ] Bot arrancando en polling (`python -m osint_suite.telegram_bot`)
- [ ] Tests de verificación pasan
- [ ] Logs configurados
- [ ] Variables de entorno configuradas (si aplica)
- [ ] Servicio `systemd` del bot configurado (si aplica)
- [ ] Backups configurados

## 🎯 Comandos Rápidos

```bash
# Instalación rápida
git clone <repo-url> osint-suite && cd osint-suite
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt && pip install -e .

# Verificación rápida
python -m osint_suite.main --menu

# Desinstalación
pip uninstall osint-suite
rm -rf venv/
```

---

**Nota**: Este proyecto es para fines educativos y de investigación. Usar responsablemente y respetar las leyes locales y términos de servicio de las plataformas.
