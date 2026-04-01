#!/usr/bin/env python3
"""
Script de instalación automatizado para OSINT Suite
"""

import os
import sys
import subprocess
import platform
from pathlib import Path

INSTALL_DEV_DEPENDENCIES = "--dev" in sys.argv


def print_banner():
    """Imprime banner de instalación"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║                    OSINT SUITE INSTALLER                     ║
║              Herramientas de Inteligencia OSINT               ║
╚══════════════════════════════════════════════════════════════╝
""")


def check_python_version():
    """Verifica la versión de Python"""
    print("[*] Verificando versión de Python...")
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print(f"[✗] Python {version.major}.{version.minor} no soportado")
        print("[!] Se requiere Python 3.8 o superior")
        return False
    print(f"[✓] Python {version.major}.{version.minor}.{version.micro} detectado")
    return True


def create_virtual_environment():
    """Crea entorno virtual"""
    print("\n[*] Creando entorno virtual...")
    venv_path = Path("venv")
    
    if venv_path.exists():
        print("[!] Entorno virtual ya existe")
        response = input("¿Recrear? (s/N): ").lower()
        if response != 's':
            return True
        import shutil
        shutil.rmtree(venv_path)
    
    try:
        subprocess.run([sys.executable, "-m", "venv", "venv"], check=True)
        print("[✓] Entorno virtual creado")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[✗] Error al crear entorno virtual: {e}")
        return False


def get_venv_python():
    """Obtiene la ruta del Python del entorno virtual"""
    if platform.system() == "Windows":
        return r"venv\Scripts\python.exe"
    else:
        return "venv/bin/python"


def get_venv_pip():
    """Obtiene la ruta del pip del entorno virtual"""
    if platform.system() == "Windows":
        return r"venv\Scripts\pip.exe"
    else:
        return "venv/bin/pip"


def install_dependencies():
    """Instala dependencias de runtime"""
    print("\n[*] Instalando dependencias...")
    pip = get_venv_pip()
    
    try:
        # Actualizar pip primero
        subprocess.run([pip, "install", "--upgrade", "pip"], check=True)
        
        # Instalar dependencias de runtime
        subprocess.run([pip, "install", "-r", "requirements.txt"], check=True)
        print("[✓] Dependencias instaladas")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[✗] Error al instalar dependencias: {e}")
        return False


def install_dev_dependencies():
    """Instala dependencias opcionales de desarrollo"""
    print("\n[*] Instalando dependencias de desarrollo...")
    pip = get_venv_pip()

    try:
        subprocess.run([pip, "install", "-r", "requirements-dev.txt"], check=True)
        print("[✓] Dependencias de desarrollo instaladas")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[✗] Error al instalar dependencias de desarrollo: {e}")
        return False


def install_package():
    """Instala el paquete osint-suite"""
    print("\n[*] Instalando paquete osint-suite...")
    pip = get_venv_pip()
    
    try:
        subprocess.run([pip, "install", "-e", "."], check=True)
        print("[✓] Paquete instalado en modo editable")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[✗] Error al instalar paquete: {e}")
        return False


def verify_installation():
    """Verifica que la instalación funciona"""
    print("\n[*] Verificando instalación...")
    python = get_venv_python()
    
    tests = [
        ("Importar utils", "from osint_suite.utils import print_banner"),
        ("Importar username_search", "from osint_suite.username_search import UsernameSearcher"),
        ("Importar email_osint", "from osint_suite.email_osint import EmailOSINT"),
        ("Importar phone_investigator", "from osint_suite.phone_investigator import PhoneInvestigator"),
        ("Importar social_analyzer", "from osint_suite.social_analyzer import SocialAnalyzer"),
        ("Importar image_metadata", "from osint_suite.image_metadata import ImageMetadataExtractor"),
        ("Importar document_analyzer", "from osint_suite.document_analyzer import DocumentAnalyzer"),
        ("Importar geolocation_helper", "from osint_suite.geolocation_helper import GeolocationHelper"),
        ("Importar breach_checker", "from osint_suite.breach_checker import BreachChecker"),
        ("Importar company_research", "from osint_suite.company_research import CompanyResearcher"),
    ]
    
    all_passed = True
    for name, import_stmt in tests:
        try:
            result = subprocess.run(
                [python, "-c", import_stmt],
                capture_output=True,
                text=True,
                check=True
            )
            print(f"  [✓] {name}")
        except subprocess.CalledProcessError as e:
            print(f"  [✗] {name}: {e.stderr}")
            all_passed = False
    
    return all_passed


def create_launcher():
    """Crea script launcher"""
    print("\n[*] Creando script launcher...")
    
    if platform.system() == "Windows":
        launcher_content = '''@echo off
call venv\\Scripts\\activate.bat
python -m osint_suite.main %*
'''
        launcher_path = "osint-suite.bat"
    else:
        launcher_content = '''#!/bin/bash
source venv/bin/activate
python -m osint_suite.main "$@"
'''
        launcher_path = "osint-suite.sh"
    
    with open(launcher_path, "w") as f:
        f.write(launcher_content)
    
    if platform.system() != "Windows":
        os.chmod(launcher_path, 0o755)
    
    print(f"[✓] Launcher creado: {launcher_path}")
    return True


def print_summary():
    """Imprime resumen de instalación"""
    print("""
╔══════════════════════════════════════════════════════════════╗
║                 INSTALACIÓN COMPLETADA                       ║
╚══════════════════════════════════════════════════════════════╝

✓ Entorno virtual creado (venv/)
✓ Dependencias instaladas
✓ Paquete osint-suite instalado
✓ Todas las herramientas verificadas

DEPENDENCIAS OPCIONALES:
  Usa `python install.py --dev` para instalar `requirements-dev.txt`.

USO:
  Windows:   venv\\Scripts\\python -m osint_suite.main --menu
  Linux/Mac: venv/bin/python -m osint_suite.main --menu

  O usar launcher:
  Windows:   osint-suite.bat --menu
  Linux/Mac: ./osint-suite.sh --menu

HERRAMIENTAS DISPONIBLES:
  1. username_search    - Búsqueda de usuarios
  2. email_osint        - Análisis de emails
  3. phone_investigator - Validación de teléfonos
  4. social_analyzer    - Análisis de redes sociales
  5. image_metadata     - Extracción de metadatos
  6. document_analyzer  - Análisis de documentos
  7. geolocation_helper - Conversión de coordenadas
  8. breach_checker     - Verificación de filtraciones
  9. company_research   - Investigación de empresas

DOCUMENTACIÓN:
  - README.md      - Guía de uso
  - DEPLOY.md      - Guía de despliegue
  - SUITE_SUMMARY.md - Resumen de herramientas

Para más información: python -m osint_suite.main --help
""")


def main():
    """Función principal de instalación"""
    print_banner()
    
    # Verificar Python
    if not check_python_version():
        sys.exit(1)
    
    # Crear entorno virtual
    if not create_virtual_environment():
        print("\n[✗] Instalación fallida: No se pudo crear entorno virtual")
        sys.exit(1)
    
    # Instalar dependencias
    if not install_dependencies():
        print("\n[✗] Instalación fallida: No se pudieron instalar dependencias")
        sys.exit(1)

    if INSTALL_DEV_DEPENDENCIES and not install_dev_dependencies():
        print("\n[✗] Instalación fallida: No se pudieron instalar dependencias de desarrollo")
        sys.exit(1)
    
    # Instalar paquete
    if not install_package():
        print("\n[✗] Instalación fallida: No se pudo instalar el paquete")
        sys.exit(1)
    
    # Verificar instalación
    if not verify_installation():
        print("\n[!] Advertencia: Algunas verificaciones fallaron")
        response = input("¿Continuar de todos modos? (s/N): ").lower()
        if response != 's':
            sys.exit(1)
    
    # Crear launcher
    create_launcher()
    
    # Imprimir resumen
    print_summary()
    
    print("\n[✓] Instalación completada exitosamente!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[!] Instalación cancelada por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n[✗] Error inesperado: {e}")
        sys.exit(1)
