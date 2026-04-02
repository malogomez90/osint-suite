# Resumen de OSINT Suite

## Suite Completa de Herramientas OSINT creada

Se ha creado una suite completa de **10 herramientas OSINT en Python**, excluyendo completamente temas de redes de internet.

---

## 📊 Herramientas Creadas

### 1. Buscador de Usuarios (`username_search.py`)
- **Función**: Verifica nombres de usuario en 50+ plataformas
- **Características**:
  - Verificación concurrente (multithreading)
  - 50+ plataformas soportadas (GitHub, Twitter, Instagram, Reddit, etc.)
  - Exportación a JSON
  - Rate limiting integrado

### 2. Email OSINT (`email_osint.py`)
- **Función**: Validación, análisis y verificación de filtraciones
- **Características**:
  - Validación de formato RFC
  - Análisis de dominio (gratuito/corporativo/temporal)
  - Generación de permutaciones de email
  - Análisis de patrones en listas de emails
  - Preparado para APIs de filtraciones

### 3. Investigador de Teléfonos (`phone_investigator.py`)
- **Función**: Validación y análisis de números telefónicos
- **Características**:
  - Validación internacional con phonenumbers
  - Identificación de operadora
  - Detección de zona horaria
  - Análisis de patrones sospechosos
  - Generación de variaciones de formato

### 4. Analizador de Redes Sociales (`social_analyzer.py`)
- **Función**: Análisis de perfiles de redes sociales
- **Características**:
  - Instagram (metadatos básicos)
  - Twitter/X (vía Nitter)
  - Reddit (API pública)
  - GitHub (API pública)
  - Análisis cross-platform
  - Detección de cross-references

### 5. Extractor de Metadatos de Imágenes (`image_metadata.py`)
- **Función**: Extracción y análisis de EXIF
- **Características**:
  - Extracción completa de EXIF
  - Decodificación de coordenadas GPS
  - Generación de enlaces a mapas
  - Análisis de riesgos de privacidad
  - Eliminación de metadatos (cleaner)
  - Procesamiento batch

### 6. Analizador de Documentos (`document_analyzer.py`)
- **Función**: Metadatos de PDF y Office
- **Características**:
  - PDF (pypdf)
  - Word (.docx con python-docx, .doc con olefile)
  - Excel (.xlsx con openpyxl, .xls con olefile)
  - Extracción de patrones (emails, URLs, teléfonos)
  - Análisis de riesgos de privacidad
  - Procesamiento batch

### 7. Herramienta de Geolocalización (`geolocation_helper.py`)
- **Función**: Conversión y análisis de coordenadas
- **Características**:
  - Parseo de múltiples formatos (decimal, DMS, etc.)
  - Conversión a DMS, UTM, MGRS
  - Cálculo de distancia (fórmula de Haversine)
  - Cálculo de rumbo/bearing
  - Generación de enlaces a múltiples servicios de mapas
  - Geocodificación inversa (Nominatim)

### 8. Verificador de Filtraciones (`breach_checker.py`)
- **Función**: Verificación de emails/usuarios en breaches
- **Características**:
  - Preparado para HaveIBeenPwned API
  - Preparado para DeHashed API
  - Generación de hashes (MD5, SHA1, SHA256, SHA512)
  - Análisis de riesgo de exposición
  - Verificación de usernames
  - Recomendaciones de seguridad

### 9. Investigación de Empresas (`company_research.py`)
- **Función**: Búsqueda en registros públicos de empresas
- **Características**:
  - Enlaces a registros por país (US, UK, ES, MX, AR, etc.)
  - OpenCorporates, Companies House, etc.
  - Plantilla de análisis estructural
  - Verificación de consistencia de datos
  - Detección de red flags

### 10. Menú Principal (`main.py`)
- **Función**: Interfaz unificada de la suite
- **Características**:
  - Menú interactivo
  - Ayuda integrada
  - Acceso a todas las herramientas

---

## 📁 Archivos de Soporte

| Archivo | Descripción |
|---------|-------------|
| `utils.py` | Utilidades comunes (colores, validaciones, exportación) |
| `requirements.txt` | Dependencias (sin herramientas de red) |
| `setup.py` | Script de instalación con entry points |
| `README.md` | Documentación completa |
| `SUITE_SUMMARY.md` | Este resumen |

---

## 🚫 Exclusiones Confirmadas

La suite **NO incluye** ninguna herramienta de:
- ❌ Dominios (whois, dns lookup, subdomains)
- ❌ IPs (geolocalización de IP, escaneo)
- ❌ DNS (resolución, enumeración)
- ❌ Escaneo de puertos/redes
- ❌ Shodan, Censys, ZoomEye, etc.
- ❌ OSINT de infraestructura de red

---

## ✅ Inclusos (OSINT Personal/Organizacional)

- ✅ Nombres de usuario
- ✅ Direcciones de email
- ✅ Números telefónicos
- ✅ Redes sociales
- ✅ Metadatos de archivos
- ✅ Geolocalización (coordenadas)
- ✅ Filtraciones de datos
- ✅ Empresas y registros públicos

---

## 🚀 Cómo Usar

### Instalación
```bash
cd awesome-osint
pip install -r requirements.txt
```

### Uso Individual
```bash
python -m osint_suite.username_search -u johndoe
python -m osint_suite.email_osint -e usuario@ejemplo.com
python -m osint_suite.phone_investigator -n "+34 612 345 678"
```

### Menú Interactivo
```bash
python -m osint_suite.main --menu
```

### Instalación como Paquete
```bash
pip install -e .
osint-suite --menu
osint-username -u johndoe
```

---

## 📊 Estadísticas

- **10 herramientas** funcionales
- **~3,500 líneas** de código Python
- **50+ plataformas** soportadas para búsqueda de usuarios
- **0 dependencias** de red/domains
- **100% Python** puro

---

## 🎯 Listo para Usar

La suite está completa y lista para:
1. Investigaciones OSINT personales
2. Verificación de identidades
3. Análisis de metadatos
4. Investigación de empresas
5. Verificación de filtraciones

**Todo sin tocar un solo tema de redes de internet.**
