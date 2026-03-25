# OSINT Suite - Herramientas de Inteligencia de Fuentes Abiertas

Suite completa de herramientas OSINT en Python, **excluyendo temas de redes de internet** (sin dominios, IPs, DNS, escaneo de redes, etc.).

## 🎯 Características

- **10 herramientas especializadas** para investigación OSINT
- **Sin dependencias de red** (no requiere dnspython, scapy, etc.)
- **Fácil de usar** con interfaz de línea de comandos
- **Exportación a JSON/CSV** para análisis posterior
- **Código modular** para integración en proyectos propios

## 🛠️ Herramientas Incluidas

| # | Herramienta | Descripción |
|---|-------------|-------------|
| 1 | **Buscador de Usuarios** | Verifica nombres de usuario en 50+ plataformas |
| 2 | **Email OSINT** | Validación, análisis y verificación de filtraciones |
| 3 | **Investigador de Teléfonos** | Validación, operadoras y análisis de números |
| 4 | **Analizador de Redes Sociales** | Perfiles de Instagram, Twitter, Reddit, GitHub |
| 5 | **Extractor de Metadatos de Imágenes** | EXIF, GPS, análisis de privacidad |
| 6 | **Analizador de Documentos** | PDF, Word, Excel, metadatos y patrones |
| 7 | **Herramienta de Geolocalización** | Conversión de coordenadas, enlaces a mapas |
| 8 | **Verificador de Filtraciones** | Chequeo de emails/usuarios en breaches |
| 9 | **Investigación de Empresas** | Búsqueda en registros públicos |
| 10 | **Menú Principal** | Interfaz unificada de la suite |

## 📦 Instalación

```bash
# Clonar o navegar al directorio
cd awesome-osint

# Crear entorno virtual (recomendado)
python -m venv venv

# Activar entorno virtual
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

## 🚀 Uso Rápido

### Modo Interactivo
```bash
python -m osint_suite.main --menu
```

### Herramientas Individuales

```bash
# 1. Buscador de Usuarios
python -m osint_suite.username_search -u johndoe --save

# 2. Email OSINT
python -m osint_suite.email_osint -e usuario@ejemplo.com

# 3. Investigador de Teléfonos
python -m osint_suite.phone_investigator -n "+34 612 345 678" --region ES

# 4. Analizador de Redes Sociales
python -m osint_suite.social_analyzer -u johndoe --cross-reference

# 5. Metadatos de Imágenes
python -m osint_suite.image_metadata -i foto.jpg --save

# 6. Analizador de Documentos
python -m osint_suite.document_analyzer -f documento.pdf

# 7. Geolocalización
python -m osint_suite.geolocation_helper --coords "40.7128, -74.0060"

# 8. Verificador de Filtraciones
python -m osint_suite.breach_checker -e usuario@ejemplo.com --risk-analysis

# 9. Investigación de Empresas
python -m osint_suite.company_research -n "Empresa Ejemplo" --country ES
```

## 📖 Uso como Librería

```python
from osint_suite.username_search import UsernameSearcher
from osint_suite.email_osint import EmailOSINT
from osint_suite.phone_investigator import PhoneInvestigator

# Buscador de Usuarios
searcher = UsernameSearcher()
results = searcher.search("johndoe")
searcher.save_results()

# Email OSINT
email_tool = EmailOSINT()
results = email_tool.investigate("usuario@ejemplo.com")
emails = email_tool.generate_email_permutations("Juan", "Perez", "empresa.com")

# Teléfono
phone_tool = PhoneInvestigator()
results = phone_tool.investigate("+14155552671")
```

## 📁 Estructura del Proyecto

```
awesome-osint/
├── osint_suite/
│   ├── __init__.py
│   ├── main.py              # Menú principal
│   ├── utils.py             # Utilidades comunes
│   ├── username_search.py   # Buscador de usuarios
│   ├── email_osint.py       # Herramienta de email
│   ├── phone_investigator.py # Investigador de teléfonos
│   ├── social_analyzer.py   # Analizador de redes sociales
│   ├── image_metadata.py    # Extractor de metadatos de imágenes
│   ├── document_analyzer.py # Analizador de documentos
│   ├── geolocation_helper.py # Herramienta de geolocalización
│   ├── breach_checker.py    # Verificador de filtraciones
│   └── company_research.py  # Investigación de empresas
├── requirements.txt
└── README_OSINT_SUITE.md
```

## ⚠️ Exclusiones (Temas de Red)

Esta suite **NO incluye** herramientas de:
- ✅ Dominios y DNS (whois, dns lookup, subdomains)
- ✅ IPs y geolocalización de IPs
- ✅ Escaneo de puertos y redes
- ✅ Shodan, Censys, etc.
- ✅ Análisis de tráfico de red
- ✅ OSINT de infraestructura

## 🔒 Consideraciones Legales y Éticas

- **Uso responsable**: Solo para investigaciones legítimas
- **Privacidad**: Respeta las leyes de privacidad de tu jurisdicción
- **Términos de servicio**: Cumple con los ToS de las plataformas consultadas
- **Rate limiting**: Las herramientas incluyen delays para no sobrecargar servicios

## 📝 Licencia

Este proyecto es para fines educativos y de investigación. Úsalo responsablemente.

## 🤝 Contribuciones

Las contribuciones son bienvenidas. Por favor:
1. Mantén el enfoque en OSINT personal/organizacional (no infraestructura de red)
2. Incluye manejo de errores apropiado
3. Documenta nuevas funcionalidades
4. Respeta el rate limiting de servicios externos

## 📧 Contacto

Para reportar problemas o sugerencias, usa el sistema de issues del repositorio.
