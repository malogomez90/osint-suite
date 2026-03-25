"""
Investigador de Números Telefónicos - Validación, operadoras y análisis
Excluye: Rastreo de ubicación en tiempo real, exploits de SS7
"""

import re
import json
import requests
from typing import Dict, List, Optional
from phonenumbers import parse, is_valid_number, format_number, PhoneNumberFormat
from phonenumbers import geocoder, carrier, timezone
import phonenumbers
from .utils import (
    Colors, print_banner, print_success, print_error, 
    print_warning, print_info, save_to_json
)


class PhoneInvestigator:
    """Herramienta de investigación de números telefónicos"""
    
    def __init__(self):
        self.results = {}
        
        # Códigos de país comunes
        self.common_country_codes = {
            '1': 'Estados Unidos/Canadá',
            '7': 'Rusia/Kazajistán',
            '33': 'Francia',
            '34': 'España',
            '39': 'Italia',
            '44': 'Reino Unido',
            '49': 'Alemania',
            '52': 'México',
            '54': 'Argentina',
            '55': 'Brasil',
            '56': 'Chile',
            '57': 'Colombia',
            '58': 'Venezuela',
            '81': 'Japón',
            '82': 'Corea del Sur',
            '86': 'China',
            '91': 'India',
            '54': 'Argentina',
            '61': 'Australia',
            '64': 'Nueva Zelanda',
            '34': 'España',
            '351': 'Portugal',
            '380': 'Ucrania',
            '54': 'Argentina',
            '593': 'Ecuador',
            '51': 'Perú',
            '598': 'Uruguay',
            '502': 'Guatemala',
            '503': 'El Salvador',
            '504': 'Honduras',
            '505': 'Nicaragua',
            '506': 'Costa Rica',
            '507': 'Panamá',
            '591': 'Bolivia',
            '595': 'Paraguay'
        }
    
    def parse_number(self, phone_number: str, default_region: str = None) -> Dict:
        """
        Parsea y valida un número telefónico
        
        Args:
            phone_number: Número a parsear
            default_region: Región por defecto (ISO 3166-1 alpha-2)
        
        Returns:
            Dict con información del número
        """
        print_info(f"Parseando número: {phone_number}")
        
        result = {
            'original': phone_number,
            'is_valid': False,
            'parsed': None,
            'error': None,
            'formats': {},
            'country': None,
            'carrier': None,
            'timezone': None,
            'is_possible': False,
            'number_type': None
        }
        
        try:
            # Limpiar el número
            cleaned = self._clean_number(phone_number)
            
            # Parsear con phonenumbers
            parsed = parse(cleaned, default_region or 'US')
            result['parsed'] = parsed
            
            # Validaciones
            result['is_valid'] = is_valid_number(parsed)
            result['is_possible'] = phonenumbers.is_possible_number(parsed)
            
            if result['is_valid']:
                # Formateos
                result['formats'] = {
                    'e164': format_number(parsed, PhoneNumberFormat.E164),
                    'international': format_number(parsed, PhoneNumberFormat.INTERNATIONAL),
                    'national': format_number(parsed, PhoneNumberFormat.NATIONAL),
                    'rfc3966': format_number(parsed, PhoneNumberFormat.RFC3966)
                }
                
                # Información geográfica
                country_code = str(parsed.country_code)
                result['country_code'] = country_code
                result['country'] = geocoder.description_for_number(parsed, 'es')
                result['country_en'] = geocoder.description_for_number(parsed, 'en')
                
                # Operadora
                try:
                    carrier_name = carrier.name_for_number(parsed, 'es')
                    if carrier_name:
                        result['carrier'] = carrier_name
                except:
                    pass
                
                # Zona horaria
                try:
                    tz = timezone.time_zones_for_number(parsed)
                    if tz:
                        result['timezone'] = list(tz)
                except:
                    pass
                
                # Tipo de número
                num_type = phonenumbers.number_type(parsed)
                type_names = {
                    phonenumbers.PhoneNumberType.MOBILE: 'Móvil',
                    phonenumbers.PhoneNumberType.FIXED_LINE: 'Fijo',
                    phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: 'Fijo o Móvil',
                    phonenumbers.PhoneNumberType.TOLL_FREE: 'Llamada gratuita',
                    phonenumbers.PhoneNumberType.PREMIUM_RATE: 'Tarifa premium',
                    phonenumbers.PhoneNumberType.VOIP: 'VoIP',
                    phonenumbers.PhoneNumberType.PERSONAL_NUMBER: 'Número personal',
                    phonenumbers.PhoneNumberType.PAGER: 'Buscapé',
                    phonenumbers.PhoneNumberType.UAN: 'UAN',
                    phonenumbers.PhoneNumberType.UNKNOWN: 'Desconocido'
                }
                result['number_type'] = type_names.get(num_type, 'Desconocido')
                
                print_success(f"Número válido detectado")
                print(f"  Formato E.164: {result['formats']['e164']}")
                print(f"  País: {result['country']}")
                if result['carrier']:
                    print(f"  Operadora: {result['carrier']}")
                print(f"  Tipo: {result['number_type']}")
                
            else:
                result['error'] = 'Número no válido según estándares internacionales'
                print_error(result['error'])
                
        except phonenumbers.NumberParseException as e:
            result['error'] = f"Error al parsear: {str(e)}"
            print_error(result['error'])
        except Exception as e:
            result['error'] = f"Error inesperado: {str(e)}"
            print_error(result['error'])
        
        return result
    
    def _clean_number(self, phone_number: str) -> str:
        """Limpia el número de caracteres no numéricos excepto +"""
        # Mantener solo dígitos y el signo + al inicio
        cleaned = ''
        for i, char in enumerate(phone_number.strip()):
            if char.isdigit():
                cleaned += char
            elif char == '+' and i == 0:
                cleaned += char
        
        return cleaned
    
    def analyze_patterns(self, phone_number: str) -> Dict:
        """
        Analiza patrones en el número telefónico
        
        Args:
            phone_number: Número a analizar
        
        Returns:
            Dict con análisis de patrones
        """
        analysis = {
            'original': phone_number,
            'length': len(phone_number),
            'digit_count': len(re.sub(r'\\D', '', phone_number)),
            'patterns': [],
            'suspicious': False,
            'risk_indicators': []
        }
        
        # Detectar patrones sospechosos
        digits_only = re.sub(r'\\D', '', phone_number)
        
        # Números repetitivos
        if re.search(r'(\\d)\\1{4,}', digits_only):
            analysis['patterns'].append('Dígitos repetitivos')
            analysis['suspicious'] = True
            analysis['risk_indicators'].append('Patrón numérico inusual (repetición)')
        
        # Secuencias
        if '123456' in digits_only or '987654' in digits_only:
            analysis['patterns'].append('Secuencia numérica')
            analysis['suspicious'] = True
            analysis['risk_indicators'].append('Secuencia numérica detectada')
        
        # Números cortos o largos
        if len(digits_only) < 7:
            analysis['patterns'].append('Número muy corto')
            analysis['suspicious'] = True
            analysis['risk_indicators'].append('Longitud inusualmente corta')
        elif len(digits_only) > 15:
            analysis['patterns'].append('Número muy largo')
            analysis['suspicious'] = True
            analysis['risk_indicators'].append('Longitud inusualmente larga')
        
        # Prefijos comunes de spam
        spam_prefixes = ['900', '803', '806', '807', '905']
        if any(digits_only.startswith(p) for p in spam_prefixes):
            analysis['patterns'].append('Prefijo de tarificación especial')
            analysis['risk_indicators'].append('Posible número de tarificación especial/premium')
        
        return analysis
    
    def generate_variations(self, phone_number: str, country_code: str = None) -> List[str]:
        """
        Genera variaciones comunes del número
        
        Args:
            phone_number: Número base
            country_code: Código de país (ej: '34' para España)
        
        Returns:
            Lista de variaciones
        """
        digits_only = re.sub(r'\\D', '', phone_number)
        variations = set()
        
        # Formato original
        variations.add(phone_number)
        
        # Solo dígitos
        variations.add(digits_only)
        
        # Con prefijo internacional
        if country_code and not digits_only.startswith(country_code):
            variations.add(f"+{country_code}{digits_only}")
            variations.add(f"00{country_code}{digits_only}")
        
        # Formatos comunes por país
        if country_code == '34' and len(digits_only) == 9:  # España
            variations.add(f"+34 {digits_only[:3]} {digits_only[3:6]} {digits_only[6:]}")
            variations.add(f"0034 {digits_only[:3]} {digits_only[3:6]} {digits_only[6:]}")
        elif country_code == '1' and len(digits_only) == 10:  # US/Canadá
            variations.add(f"+1 ({digits_only[:3]}) {digits_only[3:6]}-{digits_only[6:]}")
            variations.add(f"1-{digits_only[:3]}-{digits_only[3:6]}-{digits_only[6:]}")
        elif country_code == '52' and len(digits_only) == 10:  # México
            variations.add(f"+52 {digits_only[:3]} {digits_only[3:6]} {digits_only[6:]}")
        
        return list(variations)
    
    def batch_investigate(self, phone_numbers: List[str], default_region: str = None) -> List[Dict]:
        """
        Investiga múltiples números telefónicos
        
        Args:
            phone_numbers: Lista de números
            default_region: Región por defecto
        
        Returns:
            Lista de resultados
        """
        print_banner(f"INVESTIGACIÓN BATCH: {len(phone_numbers)} NÚMEROS")
        
        results = []
        for i, number in enumerate(phone_numbers, 1):
            print(f"\n{Colors.BOLD}[{i}/{len(phone_numbers)}]{Colors.ENDC} {number}")
            result = self.parse_number(number, default_region)
            result['patterns'] = self.analyze_patterns(number)
            results.append(result)
        
        # Resumen
        valid_count = sum(1 for r in results if r['is_valid'])
        print(f"\n{Colors.BOLD}RESUMEN:{Colors.ENDC}")
        print(f"  Total procesados: {len(results)}")
        print(f"  Válidos: {valid_count}")
        print(f"  Inválidos: {len(results) - valid_count}")
        
        return results
    
    def investigate(self, phone_number: str, default_region: str = None) -> Dict:
        """
        Realiza una investigación completa de un número telefónico
        
        Args:
            phone_number: Número a investigar
            default_region: Región por defecto
        
        Returns:
            Dict con todos los resultados
        """
        print_banner(f"INVESTIGACIÓN DE TELÉFONO: {phone_number}")
        
        results = {
            'original_number': phone_number,
            'parsing': self.parse_number(phone_number, default_region),
            'pattern_analysis': self.analyze_patterns(phone_number),
            'variations': [],
            'recommendations': []
        }
        
        # Generar variaciones si es válido
        if results['parsing']['is_valid']:
            country_code = results['parsing'].get('country_code')
            results['variations'] = self.generate_variations(phone_number, country_code)
            
            print(f"\n{Colors.BOLD}VARIACIONES DEL NÚMERO:{Colors.ENDC}")
            for var in results['variations'][:5]:  # Mostrar primeras 5
                print(f"  • {var}")
        
        # Análisis de patrones
        print(f"\n{Colors.BOLD}ANÁLISIS DE PATRONES:{Colors.ENDC}")
        pa = results['pattern_analysis']
        if pa['suspicious']:
            print_warning("Se detectaron patrones sospechosos:")
            for risk in pa['risk_indicators']:
                print_warning(f"  • {risk}")
        else:
            print_success("No se detectaron patrones sospechosos")
        
        # Recomendaciones
        recommendations = []
        
        if not results['parsing']['is_valid']:
            recommendations.append("El número no es válido internacionalmente - verificar formato")
        else:
            if results['parsing'].get('number_type') == 'Móvil':
                recommendations.append("Número móvil - posiblemente asociado a WhatsApp/Telegram")
            if results['parsing'].get('country'):
                recommendations.append(f"Verificar regulaciones de privacidad de {results['parsing']['country']}")
            if pa['suspicious']:
                recommendations.append("Precaución: patrones inusuales detectados")
        
        results['recommendations'] = recommendations
        
        print(f"\n{Colors.BOLD}RECOMENDACIONES:{Colors.ENDC}")
        for rec in recommendations:
            print_info(f"  • {rec}")
        
        self.results = results
        return results
    
    def save_results(self, filename: str = None):
        """Guarda los resultados en JSON"""
        if not filename:
            number_safe = re.sub(r'\\D', '', self.results.get('original_number', 'unknown'))
            filename = f"phone_investigation_{number_safe}"
        return save_to_json(self.results, filename)


def main():
    """Función principal para uso en línea de comandos"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Investigador de números telefónicos OSINT',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python phone_investigator.py -n "+34 612 345 678"
  python phone_investigator.py -n "612345678" --region ES
  python phone_investigator.py --batch phones.txt --region ES
  python phone_investigator.py -n "+14155552671" --save
        """
    )
    
    parser.add_argument('-n', '--number', help='Número telefónico a investigar')
    parser.add_argument('-r', '--region', default='US', 
                       help='Región por defecto (ISO 3166-1 alpha-2, ej: ES, MX, AR)')
    parser.add_argument('--batch', help='Archivo con lista de números (uno por línea)')
    parser.add_argument('--save', action='store_true', help='Guardar resultados en JSON')
    
    args = parser.parse_args()
    
    investigator = PhoneInvestigator()
    
    if args.number:
        results = investigator.investigate(args.number, args.region)
        if args.save:
            investigator.save_results()
    
    elif args.batch:
        try:
            with open(args.batch, 'r') as f:
                numbers = [line.strip() for line in f if line.strip()]
            
            results = investigator.batch_investigate(numbers, args.region)
            
            if args.save:
                save_to_json(results, f"phone_batch_investigation")
                
        except FileNotFoundError:
            print_error(f"Archivo no encontrado: {args.batch}")
        except Exception as e:
            print_error(f"Error: {str(e)}")
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
