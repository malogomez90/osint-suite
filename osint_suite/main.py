"""
OSINT Suite - Menú Principal
Suite de herramientas de Inteligencia de Fuentes Abiertas
Excluye: Dominios, IPs, DNS, escaneo de redes y temas de infraestructura de red
"""

import sys
import os
from .utils import Colors, print_banner, print_success, print_error, print_info


def show_menu():
    """Muestra el menú principal"""
    print_banner("OSINT SUITE - HERRAMIENTAS DE INTELIGENCIA")
    
    print(f"{Colors.BOLD}Herramientas disponibles:{Colors.ENDC}\n")
    
    tools = [
        ("1", "Buscador de Usuarios", "username_search", "Verifica nombres de usuario en 50+ plataformas"),
        ("2", "Email OSINT", "email_osint", "Validación, análisis y verificación de filtraciones"),
        ("3", "Investigador de Teléfonos", "phone_investigator", "Validación, operadoras y análisis de números"),
        ("4", "Analizador de Redes Sociales", "social_analyzer", "Análisis de perfiles de Instagram, Twitter, etc."),
        ("5", "Extractor de Metadatos de Imágenes", "image_metadata", "Extracción EXIF y análisis de imágenes"),
        ("6", "Analizador de Documentos", "document_analyzer", "Metadatos de PDF y documentos Office"),
        ("7", "Herramienta de Geolocalización", "geolocation_helper", "Conversión de coordenadas y enlaces a mapas"),
        ("8", "Verificador de Filtraciones", "breach_checker", "Verifica emails/usuarios en bases de datos filtradas"),
        ("9", "Investigación de Empresas", "company_research", "Búsqueda en registros públicos de empresas"),
        ("0", "Salir", None, "Cerrar la aplicación")
    ]
    
    for num, name, module, description in tools:
        if module:
            print(f"{Colors.OKCYAN}[{num}]{Colors.ENDC} {Colors.BOLD}{name}{Colors.ENDC}")
            print(f"    {description}")
        else:
            print(f"\n{Colors.FAIL}[{num}]{Colors.ENDC} {name}")
    
    print()


def run_tool(choice):
    """Ejecuta la herramienta seleccionada"""
    tools = {
        '1': ('Buscador de Usuarios', 'username_search'),
        '2': ('Email OSINT', 'email_osint'),
        '3': ('Investigador de Teléfonos', 'phone_investigator'),
        '4': ('Analizador de Redes Sociales', 'social_analyzer'),
        '5': ('Extractor de Metadatos de Imágenes', 'image_metadata'),
        '6': ('Analizador de Documentos', 'document_analyzer'),
        '7': ('Herramienta de Geolocalización', 'geolocation_helper'),
        '8': ('Verificador de Filtraciones', 'breach_checker'),
        '9': ('Investigación de Empresas', 'company_research'),
    }
    
    if choice in tools:
        name, module_name = tools[choice]
        print_banner(f"INICIANDO: {name}")
        print_info(f"Ejecutando módulo: {module_name}")
        print(f"\n{Colors.WARNING}Para usar esta herramienta, ejecuta:{Colors.ENDC}")
        print(f"  python -m osint_suite.{module_name} --help")
        print(f"\n{Colors.OKCYAN}O importa en tu código:{Colors.ENDC}")
        print(f"  from osint_suite.{module_name} import main")
        print(f"  main()")
        return True
    elif choice == '0':
        print_success("¡Hasta luego!")
        return False
    else:
        print_error("Opción no válida")
        return True


def interactive_mode():
    """Modo interactivo del menú"""
    while True:
        show_menu()
        choice = input(f"{Colors.BOLD}Selecciona una opción (0-9): {Colors.ENDC}").strip()
        
        if not run_tool(choice):
            break
        
        print()
        input(f"{Colors.OKCYAN}Presiona Enter para continuar...{Colors.ENDC}")


def show_help():
    """Muestra ayuda general"""
    print_banner("OSINT SUITE - AYUDA")
    
    print(f"{Colors.BOLD}Uso de herramientas individuales:{Colors.ENDC}\n")
    
    examples = [
        ("Buscador de Usuarios", 
         "python -m osint_suite.username_search -u johndoe --save",
         "Busca el usuario 'johndoe' en múltiples plataformas"),
        
        ("Email OSINT",
         "python -m osint_suite.email_osint -e usuario@ejemplo.com",
         "Analiza el email y genera permutaciones"),
        
        ("Investigador de Teléfonos",
         "python -m osint_suite.phone_investigator -n '+34 612 345 678' --region ES",
         "Analiza número telefónico español"),
        
        ("Analizador de Redes Sociales",
         "python -m osint_suite.social_analyzer -u johndoe --cross-reference",
         "Analiza el usuario en múltiples redes sociales"),
        
        ("Extractor de Metadatos de Imágenes",
         "python -m osint_suite.image_metadata -i foto.jpg --save",
         "Extrae metadatos EXIF de una imagen"),
        
        ("Analizador de Documentos",
         "python -m osint_suite.document_analyzer -f documento.pdf",
         "Analiza metadatos de un documento PDF"),
        
        ("Herramienta de Geolocalización",
         "python -m osint_suite.geolocation_helper --coords '40.7128, -74.0060'",
         "Analiza coordenadas GPS"),
        
        ("Verificador de Filtraciones",
         "python -m osint_suite.breach_checker -e usuario@ejemplo.com --risk-analysis",
         "Analiza riesgo de exposición del email"),
        
        ("Investigación de Empresas",
         "python -m osint_suite.company_research -n 'Empresa Ejemplo' --country ES",
         "Busca información de empresa española"),
    ]
    
    for name, command, description in examples:
        print(f"{Colors.OKCYAN}{name}:{Colors.ENDC}")
        print(f"  {Colors.BOLD}Comando:{Colors.ENDC} {command}")
        print(f"  {Colors.BOLD}Descripción:{Colors.ENDC} {description}")
        print()
    
    print(f"{Colors.WARNING}Nota:{Colors.ENDC} Todas las herramientas soportan --save para exportar resultados a JSON")


def main():
    """Función principal"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='OSINT Suite - Herramientas de Inteligencia de Fuentes Abiertas',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python -m osint_suite.main --menu          # Modo interactivo
  python -m osint_suite.main --help-tools    # Mostrar ayuda de herramientas
        """
    )
    
    parser.add_argument('--menu', action='store_true', help='Iniciar modo interactivo')
    parser.add_argument('--help-tools', action='store_true', help='Mostrar ayuda de herramientas')
    parser.add_argument('--version', action='store_true', help='Mostrar versión')
    
    args = parser.parse_args()
    
    if args.version:
        from . import __version__
        print(f"OSINT Suite v{__version__}")
        return
    
    if args.help_tools:
        show_help()
        return
    
    if args.menu or len(sys.argv) == 1:
        interactive_mode()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
