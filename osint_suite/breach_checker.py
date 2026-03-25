"""
Verificador de Filtraciones de Datos - Verifica emails/usuarios en bases de datos filtradas
Excluye: Acceso a bases de datos privadas, exploits de autenticación
"""

import hashlib
import requests
import json
import time
from typing import Dict, List, Optional, Set
from .utils import (
    Colors, print_banner, print_success, print_error, 
    print_warning, print_info, save_to_json, validate_email_format
)


class BreachChecker:
    """Verificador de filtraciones de datos"""
    
    def __init__(self):
        self.results = {}
        self.known_breach_sources = [
            'HaveIBeenPwned',
            'DeHashed',
            'LeakCheck',
            'IntelX',
            'BreachDirectory'
        ]
    
    def check_haveibeenpwned(self, email: str, api_key: str = None) -> Dict:
        """
        Verifica filtraciones en HaveIBeenPwned
        
        Args:
            email: Email a verificar
            api_key: API key (requerida para uso extensivo)
        
        Returns:
            Dict con resultados
        """
        print_info(f"Verificando HaveIBeenPwned: {email}")
        
        result = {
            'source': 'HaveIBeenPwned',
            'email': email,
            'breached': False,
            'breaches': [],
            'pastes': [],
            'error': None
        }
        
        try:
            # HaveIBeenPwned requiere API key para peticiones
            # Sin API key, solo podemos verificar el formato
            
            if not api_key:
                result['error'] = 'API key requerida para HaveIBeenPwned'
                result['note'] = 'Obtén una API key en https://haveibeenpwned.com/API/Key'
                print_warning(result['error'])
                return result
            
            url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}"
            headers = {
                'hibp-api-key': api_key,
                'User-Agent': 'OSINT-Suite-Tool'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                result['breached'] = True
                result['breaches'] = response.json()
                print_success(f"Email encontrado en {len(result['breaches'])} filtraciones")
            elif response.status_code == 404:
                result['breached'] = False
                print_success("Email no encontrado en filtraciones conocidas")
            else:
                result['error'] = f'Error HTTP {response.status_code}'
                print_error(result['error'])
                
        except Exception as e:
            result['error'] = f'Error: {str(e)}'
            print_error(result['error'])
        
        return result
    
    def check_dehashed(self, email: str, api_key: str = None) -> Dict:
        """
        Verifica filtraciones en DeHashed
        
        Args:
            email: Email a verificar
            api_key: API key para DeHashed
        
        Returns:
            Dict con resultados
        """
        print_info(f"Verificando DeHashed: {email}")
        
        result = {
            'source': 'DeHashed',
            'email': email,
            'breached': False,
            'entries': [],
            'error': None
        }
        
        try:
            if not api_key:
                result['error'] = 'API key requerida para DeHashed'
                result['note'] = 'Obtén una API key en https://www.dehashed.com/pricing'
                print_warning(result['error'])
                return result
            
            # DeHashed API requiere autenticación básica
            import base64
            credentials = base64.b64encode(f"{api_key}:".encode()).decode()
            
            url = f"https://api.dehashed.com/search?query=email:{email}"
            headers = {
                'Authorization': f'Basic {credentials}',
                'Accept': 'application/json'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('entries'):
                    result['breached'] = True
                    result['entries'] = data['entries']
                    print_success(f"Encontradas {len(result['entries'])} entradas")
                else:
                    result['breached'] = False
                    print_success("No se encontraron filtraciones")
            else:
                result['error'] = f'Error HTTP {response.status_code}'
                print_error(result['error'])
                
        except Exception as e:
            result['error'] = f'Error: {str(e)}'
            print_error(result['error'])
        
        return result
    
    def generate_email_hash(self, email: str) -> Dict:
        """
        Genera hashes comunes del email para búsqueda manual
        
        Args:
            email: Email a hashear
        
        Returns:
            Dict con diferentes hashes
        """
        email_lower = email.lower().strip()
        
        hashes = {
            'original': email,
            'lowercase': email_lower,
            'md5': hashlib.md5(email_lower.encode()).hexdigest(),
            'sha1': hashlib.sha1(email_lower.encode()).hexdigest(),
            'sha256': hashlib.sha256(email_lower.encode()).hexdigest(),
            'sha512': hashlib.sha512(email_lower.encode()).hexdigest()
        }
        
        return hashes
    
    def check_username_breach(self, username: str) -> Dict:
        """
        Verifica si un nombre de usuario ha aparecido en filtraciones
        
        Args:
            username: Nombre de usuario a verificar
        
        Returns:
            Dict con resultados
        """
        print_info(f"Verificando filtraciones de usuario: {username}")
        
        result = {
            'username': username,
            'sources_checked': [],
            'potential_breaches': [],
            'recommendations': []
        }
        
        # Nota: La mayoría de APIs requieren autenticación
        # Esta función proporciona información sobre dónde verificar
        
        result['sources_checked'] = [
            {
                'name': 'HaveIBeenPwned',
                'url': f'https://haveibeenpwned.com/',
                'note': 'Verificar manualmente o con API key',
                'supports_username': False  # HIBP solo soporta email
            },
            {
                'name': 'DeHashed',
                'url': f'https://www.dehashed.com/search?query=username:{username}',
                'note': 'Búsqueda directa disponible',
                'supports_username': True
            },
            {
                'name': 'LeakCheck',
                'url': 'https://leakcheck.io/',
                'note': 'Soporta búsqueda por username',
                'supports_username': True
            },
            {
                'name': 'IntelX',
                'url': f'https://intelx.io/?s={username}',
                'note': 'Motor de búsqueda OSINT',
                'supports_username': True
            }
        ]
        
        # Recomendaciones
        result['recommendations'] = [
            'Verificar el username en DeHashed (soporta búsqueda directa)',
            'Buscar en IntelX para encontrar menciones en filtraciones',
            'Verificar si el username está asociado a emails conocidos',
            'Revisar paste sites (Pastebin, etc.) manualmente'
        ]
        
        print(f"\n{Colors.BOLD}FUENTES PARA VERIFICAR:{Colors.ENDC}")
        for source in result['sources_checked']:
            status = f"{Colors.OKGREEN}[Soporta username]{Colors.ENDC}" if source['supports_username'] else f"{Colors.WARNING}[Email only]{Colors.ENDC}"
            print(f"  • {source['name']}: {source['url']} {status}")
        
        return result
    
    def analyze_exposure_risk(self, email: str, username: str = None) -> Dict:
        """
        Analiza el riesgo de exposición de datos
        
        Args:
            email: Email a analizar
            username: Username opcional asociado
        
        Returns:
            Dict con análisis de riesgo
        """
        print_banner(f"ANÁLISIS DE RIESGO DE EXPOSICIÓN")
        
        result = {
            'email': email,
            'username': username,
            'risk_factors': [],
            'risk_level': 'unknown',
            'recommendations': []
        }
        
        # Analizar email
        if email:
            # Validar formato
            if not validate_email_format(email):
                result['risk_factors'].append({
                    'type': 'email_format',
                    'severity': 'high',
                    'description': 'Formato de email inválido'
                })
            
            # Detectar tipo de email
            domain = email.split('@')[1].lower() if '@' in email else ''
            
            free_providers = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com']
            if domain in free_providers:
                result['risk_factors'].append({
                    'type': 'free_email',
                    'severity': 'low',
                    'description': f'Email de proveedor gratuito ({domain}) - más probable en filtraciones masivas'
                })
            
            # Verificar si parece corporativo
            if domain and domain not in free_providers:
                result['risk_factors'].append({
                    'type': 'corporate_email',
                    'severity': 'medium',
                    'description': f'Email corporativo ({domain}) - riesgo de spear phishing'
                })
        
        # Analizar username
        if username:
            # Reutilización de credenciales
            result['risk_factors'].append({
                'type': 'username_reuse',
                'severity': 'medium',
                'description': f'Username "{username}" potencialmente reutilizado en múltiples servicios'
            })
            
            # Patrones comunes
            if username.lower() in email.lower():
                result['risk_factors'].append({
                    'type': 'email_username_match',
                    'severity': 'high',
                    'description': 'Username coincide con email - facilita correlación de identidad'
                })
        
        # Calcular nivel de riesgo
        high_risks = sum(1 for r in result['risk_factors'] if r['severity'] == 'high')
        medium_risks = sum(1 for r in result['risk_factors'] if r['severity'] == 'medium')
        
        if high_risks > 0:
            result['risk_level'] = 'high'
        elif medium_risks > 1:
            result['risk_level'] = 'medium'
        else:
            result['risk_level'] = 'low'
        
        # Recomendaciones
        result['recommendations'] = [
            'Usar contraseñas únicas para cada servicio',
            'Habilitar autenticación de dos factores (2FA) en todos los servicios posibles',
            'Usar un gestor de contraseñas',
            'Monitorear regularmente haveibeenpwned.com',
            'Considerar usar emails alias/forwarding para servicios no críticos',
            'No reutilizar usernames entre servicios sensibles y públicos'
        ]
        
        # Mostrar resultados
        print(f"{Colors.BOLD}EMAIL:{Colors.ENDC} {email}")
        if username:
            print(f"{Colors.BOLD}USERNAME:{Colors.ENDC} {username}")
        
        print(f"\n{Colors.BOLD}FACTORES DE RIESGO:{Colors.ENDC}")
        for factor in result['risk_factors']:
            color = Colors.FAIL if factor['severity'] == 'high' else (Colors.WARNING if factor['severity'] == 'medium' else Colors.OKCYAN)
            print(f"  {color}[{factor['severity'].upper()}]{Colors.ENDC} {factor['description']}")
        
        risk_colors = {
            'high': Colors.FAIL,
            'medium': Colors.WARNING,
            'low': Colors.OKGREEN,
            'unknown': Colors.OKCYAN
        }
        
        print(f"\n{Colors.BOLD}NIVEL DE RIESGO:{Colors.ENDC} {risk_colors.get(result['risk_level'], Colors.OKCYAN)}{result['risk_level'].upper()}{Colors.ENDC}")
        
        print(f"\n{Colors.BOLD}RECOMENDACIONES:{Colors.ENDC}")
        for rec in result['recommendations']:
            print(f"  • {rec}")
        
        self.results = result
        return result
    
    def comprehensive_check(self, email: str, username: str = None, api_keys: Dict = None) -> Dict:
        """
        Realiza verificación completa de filtraciones
        
        Args:
            email: Email a verificar
            username: Username opcional
            api_keys: Dict con API keys {'haveibeenpwned': 'key', 'dehashed': 'key'}
        
        Returns:
            Dict con resultados completos
        """
        print_banner(f"VERIFICACIÓN COMPLETA DE FILTRACIONES")
        
        api_keys = api_keys or {}
        
        results = {
            'email': email,
            'username': username,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'checks': {},
            'hashes': {},
            'risk_analysis': None,
            'summary': {
                'breaches_found': 0,
                'total_sources_checked': 0,
                'requires_manual_verification': []
            }
        }
        
        # Generar hashes
        print(f"{Colors.BOLD}GENERANDO HASHES...{Colors.ENDC}")
        results['hashes'] = self.generate_email_hash(email)
        print(f"  MD5: {results['hashes']['md5']}")
        print(f"  SHA1: {results['hashes']['sha1']}")
        print(f"  SHA256: {results['hashes']['sha256']}")
        
        # Verificaciones automáticas (si hay API keys)
        print(f"\n{Colors.BOLD}VERIFICACIONES AUTOMÁTICAS:{Colors.ENDC}")
        
        if api_keys.get('haveibeenpwned'):
            hibp_result = self.check_haveibeenpwned(email, api_keys['haveibeenpwned'])
            results['checks']['haveibeenpwned'] = hibp_result
            results['summary']['total_sources_checked'] += 1
            if hibp_result.get('breached'):
                results['summary']['breaches_found'] += len(hibp_result.get('breaches', []))
        else:
            print_warning("HaveIBeenPwned: Sin API key - omitiendo verificación automática")
            results['summary']['requires_manual_verification'].append({
                'source': 'HaveIBeenPwned',
                'url': 'https://haveibeenpwned.com/',
                'reason': 'API key requerida'
            })
        
        if api_keys.get('dehashed'):
            dehashed_result = self.check_dehashed(email, api_keys['dehashed'])
            results['checks']['dehashed'] = dehashed_result
            results['summary']['total_sources_checked'] += 1
            if dehashed_result.get('breached'):
                results['summary']['breaches_found'] += len(dehashed_result.get('entries', []))
        else:
            print_warning("DeHashed: Sin API key - omitiendo verificación automática")
            results['summary']['requires_manual_verification'].append({
                'source': 'DeHashed',
                'url': 'https://www.dehashed.com/',
                'reason': 'API key requerida'
            })
        
        # Verificación de username
        if username:
            print(f"\n{Colors.BOLD}VERIFICACIÓN DE USERNAME:{Colors.ENDC}")
            username_result = self.check_username_breach(username)
            results['checks']['username'] = username_result
        
        # Análisis de riesgo
        print(f"\n{Colors.BOLD}ANÁLISIS DE RIESGO:{Colors.ENDC}")
        risk_result = self.analyze_exposure_risk(email, username)
        results['risk_analysis'] = risk_result
        
        # Resumen final
        print(f"\n{Colors.BOLD}RESUMEN:{Colors.ENDC}")
        print(f"  Fuentes verificadas: {results['summary']['total_sources_checked']}")
        print(f"  Filtraciones encontradas: {results['summary']['breaches_found']}")
        if results['summary']['requires_manual_verification']:
            print(f"  Requieren verificación manual: {len(results['summary']['requires_manual_verification'])}")
        
        self.results = results
        return results
    
    def save_results(self, filename: str = None):
        """Guarda los resultados en JSON"""
        if not filename:
            email_safe = self.results.get('email', 'unknown').replace('@', '_at_')
            filename = f"breach_check_{email_safe}"
        return save_to_json(self.results, filename)


def main():
    """Función principal para uso en línea de comandos"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Verificador de Filtraciones de Datos OSINT',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python breach_checker.py -e usuario@ejemplo.com
  python breach_checker.py -e usuario@ejemplo.com -u miusername
  python breach_checker.py -e usuario@ejemplo.com --risk-analysis
  python breach_checker.py --hash usuario@ejemplo.com
        """
    )
    
    parser.add_argument('-e', '--email', help='Email a verificar')
    parser.add_argument('-u', '--username', help='Username asociado')
    parser.add_argument('--risk-analysis', action='store_true', help='Solo análisis de riesgo')
    parser.add_argument('--hash', help='Generar hashes del email')
    parser.add_argument('--hibp-key', help='API key de HaveIBeenPwned')
    parser.add_argument('--dehashed-key', help='API key de DeHashed')
    parser.add_argument('--save', action='store_true', help='Guardar resultados en JSON')
    
    args = parser.parse_args()
    
    checker = BreachChecker()
    
    if args.hash:
        hashes = checker.generate_email_hash(args.hash)
        print_banner(f"HASHES DE EMAIL")
        print(f"Email: {hashes['original']}")
        print(f"\nMD5:    {hashes['md5']}")
        print(f"SHA1:   {hashes['sha1']}")
        print(f"SHA256: {hashes['sha256']}")
        print(f"SHA512: {hashes['sha512']}")
    
    elif args.risk_analysis and args.email:
        checker.analyze_exposure_risk(args.email, args.username)
        if args.save:
            checker.save_results()
    
    elif args.email:
        api_keys = {}
        if args.hibp_key:
            api_keys['haveibeenpwned'] = args.hibp_key
        if args.dehashed_key:
            api_keys['dehashed'] = args.dehashed_key
        
        results = checker.comprehensive_check(args.email, args.username, api_keys)
        if args.save:
            checker.save_results()
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
