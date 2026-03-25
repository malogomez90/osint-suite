"""
Utilidades comunes para todas las herramientas OSINT
"""

import re
import json
import csv
import requests
from datetime import datetime
from typing import Dict, List, Optional, Any
from urllib.parse import quote, unquote


class Colors:
    """Colores para terminal"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_banner(text: str):
    """Imprime un banner decorativo"""
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}{text.center(60)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}\n")


def print_success(message: str):
    """Imprime mensaje de éxito"""
    print(f"{Colors.OKGREEN}[✓] {message}{Colors.ENDC}")


def print_error(message: str):
    """Imprime mensaje de error"""
    print(f"{Colors.FAIL}[✗] {message}{Colors.ENDC}")


def print_warning(message: str):
    """Imprime mensaje de advertencia"""
    print(f"{Colors.WARNING}[!] {message}{Colors.ENDC}")


def print_info(message: str):
    """Imprime mensaje informativo"""
    print(f"{Colors.OKCYAN}[i] {message}{Colors.ENDC}")


def save_to_json(data: Any, filename: str):
    """Guarda datos en formato JSON"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename}_{timestamp}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print_success(f"Datos guardados en: {filename}")
    return filename


def save_to_csv(data: List[Dict], filename: str, fieldnames: List[str] = None):
    """Guarda datos en formato CSV"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{filename}_{timestamp}.csv"
    
    if not data:
        print_warning("No hay datos para guardar")
        return None
    
    if not fieldnames:
        fieldnames = list(data[0].keys())
    
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
    
    print_success(f"Datos guardados en: {filename}")
    return filename


def validate_email_format(email: str) -> bool:
    """Valida el formato de un email"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_phone_format(phone: str) -> bool:
    """Valida el formato básico de un teléfono"""
    # Elimina espacios, guiones, paréntesis, etc.
    cleaned = re.sub(r'[\s\-\(\)\.]', '', phone)
    # Debe tener al menos 7 dígitos y máximo 15 (estándar E.164)
    return cleaned.isdigit() and 7 <= len(cleaned) <= 15


def clean_username(username: str) -> str:
    """Limpia un nombre de usuario"""
    # Elimina @ al inicio si existe
    username = username.lstrip('@')
    # Elimina espacios
    username = username.strip()
    return username


def make_request(url: str, headers: Dict = None, timeout: int = 10) -> Optional[requests.Response]:
    """Realiza una petición HTTP segura"""
    default_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    if headers:
        default_headers.update(headers)
    
    try:
        response = requests.get(url, headers=default_headers, timeout=timeout)
        return response
    except requests.RequestException as e:
        print_error(f"Error en la petición: {str(e)}")
        return None


def format_timestamp(timestamp: Any) -> str:
    """Formatea un timestamp a string legible"""
    if isinstance(timestamp, (int, float)):
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    elif isinstance(timestamp, datetime):
        return timestamp.strftime("%Y-%m-%d %H:%M:%S")
    return str(timestamp)


def extract_urls(text: str) -> List[str]:
    """Extrae URLs de un texto"""
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    return re.findall(url_pattern, text)


def sanitize_filename(filename: str) -> str:
    """Sanitiza un nombre de archivo"""
    # Elimina caracteres no permitidos
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Limita longitud
    if len(filename) > 200:
        filename = filename[:200]
    return filename
