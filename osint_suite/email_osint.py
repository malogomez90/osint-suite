"""
Herramienta de Email OSINT - Validación, verificación de filtraciones y análisis
Excluye: Envío de emails, exploits de servidor
"""

import re
import hashlib
import requests
import json
import time
from typing import Dict, List, Optional, Tuple
from email.utils import parseaddr
from .utils import (
    Colors, print_banner, print_success, print_error, 
    print_warning, print_info, validate_email_format, 
    save_to_json, make_request
)


class EmailOSINT:
    """Herramienta de investigación de direcciones de email"""
    
    def __init__(self):
        self.results = {}
        self.breach_apis = {
            'haveibeenpwned': 'https://haveibeenpwned.com/api/v3/breachedaccount/{}',
            'emailrep': 'https://emailrep.io/{}'
        }
    
    def validate_email(self, email: str) -> Dict:
        """
        Valida la sintaxis y estructura de un email
        
        Returns:
            Dict con información de validación
        """
        print_info(f"Validando formato de email: {email}")
        
        result = {
            'email': email,
            'is_valid': False,
            'local_part': None,
            'domain': None,
            'errors': []
        }
        
        # Validación básica de formato
        if not email or '@' not in email:
            result['errors'].append('Formato inválido: falta @')
            return result
        
        # Parseo con email.utils
        parsed_name, parsed_email = parseaddr(email)
        if not parsed_email:
            result['errors'].append('No se pudo parsear el email')
            return result
        
        # Validación con regex
        if not validate_email_format(email):
            result['errors'].append('Formato no coincide con estándar RFC')
            return result
        
        # Separar local y dominio
        try:
            local_part, domain = email.rsplit('@', 1)
            result['local_part'] = local_part
            result['domain'] = domain
            result['is_valid'] = True
            
            # Análisis adicional del local_part
            result['local_analysis'] = self._analyze_local_part(local_part)
            
            # Análisis del dominio
            result['domain_analysis'] = self._analyze_domain(domain)
            
        except ValueError:
            result['errors'].append('Error al separar local/dominio')
        
        return result
    
    def _analyze_local_part(self, local: str) -> Dict:
        """Analiza la parte local del email"""
        analysis = {
            'length': len(local),
            'has_dots': '.' in local,
            'has_underscores': '_' in local,
            'has_hyphens': '-' in local,
            'has_numbers': bool(re.search(r'\\d', local)),
            'has_plus': '+' in local,  # Posible alias
            'possible_alias': False,
            'possible_role': False
        }
        
        # Detectar alias (ej: usuario+alias@dominio.com)
        if '+' in local:
            analysis['possible_alias'] = True
            analysis['base_username'] = local.split('+')[0]
        
        # Detectar emails de roles
        role_patterns = [
            'admin', 'support', 'info', 'contact', 'sales', 
            'marketing', 'help', 'webmaster', 'postmaster',
            'noreply', 'no-reply', 'team', 'hello', 'office'
        ]
        local_lower = local.lower()
        analysis['possible_role'] = any(role in local_lower for role in role_patterns)
        analysis['is_role_account'] = local_lower in role_patterns
        
        return analysis
    
    def _analyze_domain(self, domain: str) -> Dict:
        """Analiza el dominio del email"""
        analysis = {
            'domain': domain,
            'is_free_provider': False,
            'is_corporate': False,
            'is_temporary': False,
            'provider_type': 'unknown'
        }
        
        # Proveedores de email gratuitos comunes
        free_providers = [
            'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
            'aol.com', 'icloud.com', 'me.com', 'mac.com',
            'protonmail.com', 'proton.me', 'tutanota.com',
            'zoho.com', 'yandex.com', 'mail.ru', 'gmx.com',
            'live.com', 'msn.com', 'qq.com', '163.com',
            '126.com', 'sina.com', 'sohu.com', 'foxmail.com',
            'hey.com', 'fastmail.com', 'runbox.com'
        ]
        
        # Proveedores temporales/desechables
        temp_providers = [
            'tempmail.com', 'throwaway.com', 'mailinator.com',
            'guerrillamail.com', '10minutemail.com', 'yopmail.com',
            'sharklasers.com', 'spamgourmet.com', 'getairmail.com',
            'temp-mail.org', 'fakeinbox.com', 'tempinbox.com',
            'mailnesia.com', 'tempmailaddress.com', 'burnermail.io'
        ]
        
        domain_lower = domain.lower()
        
        if domain_lower in free_providers:
            analysis['is_free_provider'] = True
            analysis['provider_type'] = 'free'
        elif domain_lower in temp_providers or 'temp' in domain_lower or 'throw' in domain_lower:
            analysis['is_temporary'] = True
            analysis['provider_type'] = 'temporary'
        elif domain.count('.') >= 1 and len(domain) > 4:
            analysis['is_corporate'] = True
            analysis['provider_type'] = 'corporate'
        
        return analysis
    
    def check_breach_status(self, email: str) -> Dict:
        """
        Verifica si el email ha aparecido en filtraciones de datos
        Nota: Usa APIs públicas con rate limiting
        """
        print_info(f"Verificando filtraciones para: {email}")
        
        result = {
            'email': email,
            'breaches_found': False,
            'breach_count': 0,
            'breaches': [],
            'pastes_found': False,
            'error': None
        }
        
        try:
            # Usar HaveIBeenPwned API (requiere API key para uso extensivo)
            # Aquí simulamos con una petición de ejemplo
            # En producción, necesitarías una API key
            
            hibp_url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}"
            headers = {
                'User-Agent': 'OSINT-Suite-Tool',
                'Accept': 'application/json'
            }
            
            # Simulación de respuesta (en producción, hacer petición real con API key)
            # response = make_request(hibp_url, headers=headers)
            
            print_warning("Verificación de filtraciones requiere API key de HaveIBeenPwned")
            print_info("Visita: https://haveibeenpwned.com/API/Key para obtener una API key")
            
        except Exception as e:
            result['error'] = str(e)
            print_error(f"Error al verificar filtraciones: {str(e)}")
        
        return result
    
    def generate_email_permutations(self, first_name: str, last_name: str, domain: str) -> List[str]:
        """
        Genera permutaciones comunes de emails basadas en nombre y apellido
        
        Args:
            first_name: Nombre
            last_name: Apellido
            domain: Dominio del email
        
        Returns:
            Lista de posibles emails
        """
        first = first_name.lower().strip()
        last = last_name.lower().strip()
        f_initial = first[0] if first else ''
        l_initial = last[0] if last else ''
        
        patterns = [
            f"{first}@{domain}",
            f"{last}@{domain}",
            f"{first}.{last}@{domain}",
            f"{first}_{last}@{domain}",
            f"{first}-{last}@{domain}",
            f"{first}{last}@{domain}",
            f"{f_initial}{last}@{domain}",
            f"{f_initial}.{last}@{domain}",
            f"{first}{l_initial}@{domain}",
            f"{first}.{l_initial}@{domain}",
            f"{f_initial}{l_initial}@{domain}",
            f"{last}.{first}@{domain}",
            f"{last}_{first}@{domain}",
            f"{last}{f_initial}@{domain}",
            f"{first}{last[0:3]}@{domain}" if len(last) >= 3 else f"{first}{last}@{domain}",
        ]
        
        # Eliminar duplicados manteniendo orden
        seen = set()
        unique_patterns = []
        for pattern in patterns:
            if pattern not in seen:
                seen.add(pattern)
                unique_patterns.append(pattern)
        
        return unique_patterns
    
    def analyze_email_patterns(self, emails: List[str]) -> Dict:
        """
        Analiza patrones en una lista de emails
        
        Args:
            emails: Lista de direcciones de email
        
        Returns:
            Dict con análisis de patrones
        """
        analysis = {
            'total_emails': len(emails),
            'domains': {},
            'patterns': {},
            'common_local_parts': []
        }
        
        local_parts = []
        
        for email in emails:
            if not validate_email_format(email):
                continue
            
            try:
                local, domain = email.rsplit('@', 1)
                local_parts.append(local)
                
                # Contar dominios
                analysis['domains'][domain] = analysis['domains'].get(domain, 0) + 1
                
                # Detectar patrones
                if '.' in local:
                    analysis['patterns']['dot_separator'] = analysis['patterns'].get('dot_separator', 0) + 1
                if '_' in local:
                    analysis['patterns']['underscore_separator'] = analysis['patterns'].get('underscore_separator', 0) + 1
                if '-' in local:
                    analysis['patterns']['hyphen_separator'] = analysis['patterns'].get('hyphen_separator', 0) + 1
                if re.search(r'\\d', local):
                    analysis['patterns']['contains_numbers'] = analysis['patterns'].get('contains_numbers', 0) + 1
                if '+' in local:
                    analysis['patterns']['plus_alias'] = analysis['patterns'].get('plus_alias', 0) + 1
                    
            except ValueError:
                continue
        
        # Encontrar partes locales comunes
        from collections import Counter
        local_counter = Counter(local_parts)
        analysis['common_local_parts'] = local_counter.most_common(10)
        
        return analysis
    
    def investigate(self, email: str, check_breach: bool = True) -> Dict:
        """
        Realiza una investigación completa de un email
        
        Args:
            email: Dirección de email a investigar
            check_breach: Si se debe verificar filtraciones
        
        Returns:
            Dict con todos los resultados
        """
        print_banner(f"INVESTIGACIÓN DE EMAIL: {email}")
        
        results = {
            'email': email,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'validation': None,
            'breach_check': None,
            'recommendations': []
        }
        
        # Validación
        print(f"\n{Colors.BOLD}[1] VALIDACIÓN DE FORMATO{Colors.ENDC}")
        validation = self.validate_email(email)
        results['validation'] = validation
        
        if validation['is_valid']:
            print_success("Formato de email válido")
            print(f"  Local part: {validation['local_part']}")
            print(f"  Dominio: {validation['domain']}")
            
            # Mostrar análisis del local part
            if 'local_analysis' in validation:
                la = validation['local_analysis']
                print(f"\n  {Colors.BOLD}Análisis de usuario:{Colors.ENDC}")
                print(f"    Longitud: {la['length']} caracteres")
                if la['possible_alias']:
                    print_warning("    Posible alias detectado (+)")
                if la['possible_role']:
                    print_warning("    Parece ser cuenta de rol/función")
                if la['is_role_account']:
                    print_warning("    Es una cuenta de rol genérica")
            
            # Mostrar análisis del dominio
            if 'domain_analysis' in validation:
                da = validation['domain_analysis']
                print(f"\n  {Colors.BOLD}Análisis de dominio:{Colors.ENDC}")
                print(f"    Tipo: {da['provider_type']}")
                if da['is_free_provider']:
                    print_info("    Proveedor de email gratuito")
                if da['is_temporary']:
                    print_warning("    Posible email temporal/desechable")
                if da['is_corporate']:
                    print_success("    Dominio corporativo detectado")
        else:
            print_error("Formato de email inválido")
            for error in validation['errors']:
                print_error(f"  - {error}")
            return results
        
        # Verificación de filtraciones
        if check_breach:
            print(f"\n{Colors.BOLD}[2] VERIFICACIÓN DE FILTRACIONES{Colors.ENDC}")
            breach_info = self.check_breach_status(email)
            results['breach_check'] = breach_info
        
        # Recomendaciones
        print(f"\n{Colors.BOLD}[3] RECOMENDACIONES{Colors.ENDC}")
        recommendations = []
        
        da = validation.get('domain_analysis', {})
        la = validation.get('local_analysis', {})
        
        if da.get('is_temporary'):
            recommendations.append("Email temporal - alta probabilidad de ser desechable")
        if da.get('is_free_provider'):
            recommendations.append("Email de proveedor gratuito - verificar autenticidad")
        if la.get('is_role_account'):
            recommendations.append("Cuenta de rol - probablemente no es personal")
        if la.get('possible_alias'):
            recommendations.append("Posible alias - el usuario base podría ser diferente")
        if not da.get('is_free_provider') and not da.get('is_temporary'):
            recommendations.append("Dominio corporativo - verificar si la empresa existe")
        
        if not recommendations:
            recommendations.append("No se detectaron patrones de riesgo específicos")
        
        for rec in recommendations:
            print_info(f"  • {rec}")
        
        results['recommendations'] = recommendations
        
        self.results = results
        return results
    
    def save_results(self, filename: str = None):
        """Guarda los resultados en JSON"""
        if not filename:
            email_safe = self.results.get('email', 'unknown').replace('@', '_at_')
            filename = f"email_investigation_{email_safe}"
        return save_to_json(self.results, filename)


def main():
    """Función principal para uso en línea de comandos"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Herramienta de investigación de emails OSINT',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python email_osint.py -e usuario@ejemplo.com
  python email_osint.py -e usuario@ejemplo.com --no-breach
  python email_osint.py --permute "Juan" "Perez" "empresa.com"
  python email_osint.py --analyze-list emails.txt
        """
    )
    
    parser.add_argument('-e', '--email', help='Email a investigar')
    parser.add_argument('--no-breach', action='store_true', help='No verificar filtraciones')
    parser.add_argument('--permute', nargs=3, metavar=('NOMBRE', 'APELLIDO', 'DOMINIO'),
                       help='Generar permutaciones de email')
    parser.add_argument('--analyze-list', help='Archivo con lista de emails para analizar')
    parser.add_argument('--save', action='store_true', help='Guardar resultados en JSON')
    
    args = parser.parse_args()
    
    investigator = EmailOSINT()
    
    if args.email:
        results = investigator.investigate(args.email, not args.no_breach)
        if args.save:
            investigator.save_results()
    
    elif args.permute:
        first, last, domain = args.permute
        print_banner(f"GENERANDO PERMUTACIONES: {first} {last}")
        permutations = investigator.generate_email_permutations(first, last, domain)
        print(f"{Colors.OKCYAN}Posibles emails generados:{Colors.ENDC}")
        for email in permutations:
            print(f"  • {email}")
        print(f"\nTotal: {len(permutations)} permutaciones")
    
    elif args.analyze_list:
        print_banner(f"ANALIZANDO LISTA DE EMAILS")
        try:
            with open(args.analyze_list, 'r') as f:
                emails = [line.strip() for line in f if line.strip()]
            
            print_info(f"Cargados {len(emails)} emails desde {args.analyze_list}")
            analysis = investigator.analyze_email_patterns(emails)
            
            print(f"\n{Colors.BOLD}RESULTADOS DEL ANÁLISIS:{Colors.ENDC}")
            print(f"Total analizados: {analysis['total_emails']}")
            
            print(f"\n{Colors.BOLD}Dominios encontrados:{Colors.ENDC}")
            for domain, count in sorted(analysis['domains'].items(), key=lambda x: x[1], reverse=True):
                print(f"  • {domain}: {count} emails")
            
            print(f"\n{Colors.BOLD}Patrones detectados:{Colors.ENDC}")
            for pattern, count in analysis['patterns'].items():
                print(f"  • {pattern}: {count} ocurrencias")
            
            if args.save:
                save_to_json(analysis, f"email_pattern_analysis")
                
        except FileNotFoundError:
            print_error(f"Archivo no encontrado: {args.analyze_list}")
        except Exception as e:
            print_error(f"Error al analizar lista: {str(e)}")
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
