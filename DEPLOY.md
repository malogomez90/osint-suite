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
| PyPDF2 | >=3.0.0 | Análisis de PDF |
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

Configuración mínima por entorno:

```bash
export TELEGRAM_BOT_TOKEN="tu_token"
export TELEGRAM_RATE_LIMIT_PER_MINUTE=5
export TELEGRAM_RATE_LIMIT_PER_HOUR=20
export TELEGRAM_LONG_JOB_THRESHOLD_SECONDS=5
```

Arranque local:

```bash
python -m osint_suite.telegram_bot
```

Verificación manual mínima:

```bash
# Validar configuración sin arrancar polling
python -m osint_suite.telegram_bot --check-config

# Después, arrancar el bot y probar en Telegram:
# /start
# /help
# /username johndoe
# /email usuario@ejemplo.com
```

Notas operativas:

- El token solo debe ir en variables de entorno.
- El bot aplica rate limiting por `user_id`.
- Los resultados grandes se envían como JSON adjunto en el chat.

## 📊 Monitoreo

### Logs

Los logs se guardan automáticamente en:
- Linux: `/var/log/osint-suite/`
- Windows: `%APPDATA%\osint-suite\logs\`
- macOS: `~/Library/Logs/osint-suite/`

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
- [ ] Tests de verificación pasan
- [ ] Logs configurados
- [ ] Variables de entorno configuradas (si aplica)
- [ ] Servicio systemd configurado (si aplica)
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
