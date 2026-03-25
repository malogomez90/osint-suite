"""
Herramienta de Investigación de Empresas - Búsqueda en registros públicos de empresas
Excluye: Acceso a bases de datos privadas, scraping de información confidencial
"""

import re
import json
import requests
from typing import Dict, List, Optional
from datetime import datetime
from .utils import (
    Colors, print_banner, print_success, print_error, 
    print_warning, print_info, save_to_json, make_request
)


class CompanyResearcher:
    """Herramienta de investigación de empresas"""
    
    def __init__(self):
        self.results = {}
        
        # Registros de empresas por país (URLs públicas)
        self.company_registers = {
            'US': {
                'SEC EDGAR': 'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={}',
                'OpenCorporates': 'https://opencorporates.com/companies?jurisdiction_code=&q={}&utf8=%E2%9C%93',
                'state': 'Varía por estado (Secretary of State)'
            },
            'UK': {
                'Companies House': 'https://find-and-update.company-information.service.gov.uk/search?q={}',
                'OpenCorporates': 'https://opencorporates.com/companies/gb?q={}'
            },
            'ES': {
                'eInforma': 'https://www.einforma.com/servlet/app/portal/ENTP/prod/LIBDIRECTORIO?tipo=1&nif={}',
                'OpenCorporates': 'https://opencorporates.com/companies/es?q={}'
            },
            'MX': {
                'SIEM': 'https://www.siem.gob.mx/siem/portal/consultas/empresas',
                'OpenCorporates': 'https://opencorporates.com/companies/mx?q={}'
            },
            'AR': {
                'AFIP': 'https://www.afip.gob.ar/genericos/guiasDeTramites/guia/5',
                'OpenCorporates': 'https://opencorporates.com/companies/ar?q={}'
            },
            'CL': {
                'OpenCorporates': 'https://opencorporates.com/companies/cl?q={}'
            },
            'CO': {
                'RUES': 'https://www.rues.org.co/',
                'OpenCorporates': 'https://opencorporates.com/companies/co?q={}'
            },
            'PE': {
                'SUNAT': 'https://e-consultaruc.sunat.gob.pe/cl-ti-itmrconsruc/jcrS00Alias',
                'OpenCorporates': 'https://opencorporates.com/companies/pe?q={}'
            },
            'DE': {
                'Handelsregister': 'https://www.handelsregister.de/',
                'OpenCorporates': 'https://opencorporates.com/companies/de?q={}'
            },
            'FR': {
                'Pappers': 'https://www.pappers.fr/rechercher-une-societe',
                'OpenCorporates': 'https://opencorporates.com/companies/fr?q={}'
            },
            'IT': {
                'Registro Imprese': 'https://registroimprese.ccsmc.it/',
                'OpenCorporates': 'https://opencorporates.com/companies/it?q={}'
            },
            'Global': {
                'OpenCorporates': 'https://opencorporates.com/companies?q={}',
                'Crunchbase': 'https://www.crunchbase.com/textsearch?q={}',
                'LinkedIn': 'https://www.linkedin.com/company/{}',
                'Wikipedia': 'https://en.wikipedia.org/wiki/{}'
            }
        }
    
    def search_company(self, company_name: str, country_code: str = None) -> Dict:
        """
        Busca información sobre una empresa en registros públicos
        
        Args:
            company_name: Nombre de la empresa
            country_code: Código de país opcional (ISO 3166-1 alpha-2)
        
        Returns:
            Dict con información y enlaces a registros
        """
        print_banner(f"INVESTIGACIÓN DE EMPRESA: {company_name}")
        
        result = {
            'company_name': company_name,
            'search_timestamp': datetime.now().isoformat(),
            'country_code': country_code,
            'registers_to_check': [],
            'direct_links': {},
            'recommendations': [],
            'notes': []
        }
        
        # Normalizar nombre para URLs
        company_encoded = requests.utils.quote(company_name)
        company_slug = company_name.lower().replace(' ', '-').replace('.', '')
        
        print(f"{Colors.BOLD}BÚSQUEDA DE REGISTROS:{Colors.ENDC}")
        
        # Si se especificó país, mostrar registros específicos
        if country_code and country_code.upper() in self.company_registers:
            country_code = country_code.upper()
            registers = self.company_registers[country_code]
            
            print(f"\n{Colors.OKCYAN}Registros para {country_code}:{Colors.ENDC}")
            for register_name, url_template in registers.items():
                if '{}' in url_template:
                    url = url_template.format(company_encoded)
                else:
                    url = url_template
                
                result['registers_to_check'].append({
                    'name': register_name,
                    'url': url,
                    'type': 'official' if register_name != 'OpenCorporates' else 'aggregator'
                })
                
                print(f"  • {register_name}: {url}")
        
        # Mostrar registros globales siempre
        print(f"\n{Colors.OKCYAN}Fuentes globales:{Colors.ENDC}")
        global_registers = self.company_registers['Global']
        
        for register_name, url_template in global_registers.items():
            if '{}' in url_template:
                if register_name == 'LinkedIn':
                    url = url_template.format(company_slug)
                else:
                    url = url_template.format(company_encoded)
            else:
                url = url_template
            
            result['direct_links'][register_name] = url
            print(f"  • {register_name}: {url}")
        
        # Generar recomendaciones
        result['recommendations'] = self._generate_recommendations(company_name, country_code)
        
        print(f"\n{Colors.BOLD}RECOMENDACIONES DE BÚSQUEDA:{Colors.ENDC}")
        for rec in result['recommendations']:
            print(f"  • {rec}")
        
        # Notas importantes
        result['notes'] = [
            'Algunos registros requieren registro gratuito para acceso completo',
            'La información disponible varía según el país y tipo de empresa',
            'Empresas privadas tienen menos información pública que las públicas',
            'Verificar siempre múltiples fuentes para confirmar datos'
        ]
        
        print(f"\n{Colors.WARNING}NOTAS:{Colors.ENDC}")
        for note in result['notes']:
            print(f"  ! {note}")
        
        self.results = result
        return result
    
    def _generate_recommendations(self, company_name: str, country_code: str = None) -> List[str]:
        """Genera recomendaciones de búsqueda específicas"""
        recommendations = []
        
        # Búsquedas generales
        recommendations.append(f"Buscar '{company_name}' en OpenCorporates (agregador global)")
        recommendations.append(f"Verificar presencia en LinkedIn de la empresa")
        recommendations.append(f"Buscar '{company_name}' en Google News para noticias recientes")
        
        # Recomendaciones específicas por país
        if country_code:
            country_tips = {
                'US': [
                    'Verificar en SEC EDGAR si es empresa pública (CIK number)',
                    'Buscar en Secretary of State del estado de incorporación',
                    'Verificar EIN (Employer Identification Number) en IRS'
                ],
                'UK': [
                    'Buscar en Companies House (número de empresa gratuito)',
                    'Verificar si está en Companies House Beta para información actualizada'
                ],
                'ES': [
                    'Buscar en eInforma con el NIF/CIF si se conoce',
                    'Verificar en Registro Mercantil de la provincia',
                    'Consultar en BORME (Boletín Oficial del Registro Mercantil)'
                ],
                'MX': [
                    'Buscar en SIEM (Sistema de Información Empresarial Mexicano)',
                    'Verificar en SAT si se conoce el RFC'
                ],
                'AR': [
                    'Verificar CUIT en AFIP',
                    'Buscar en IGJ (Inspección General de Justicia) si es sociedad'
                ]
            }
            
            if country_code in country_tips:
                recommendations.extend(country_tips[country_code])
        
        # Recomendaciones de OSINT
        recommendations.extend([
            'Buscar dominios web asociados (whois history)',
            'Verificar presencia en redes sociales corporativas',
            'Buscar en Wayback Machine para versiones históricas de web',
            'Revisar Glassdoor/Indeed para información de empleados'
        ])
        
        return recommendations
    
    def analyze_company_structure(self, company_name: str) -> Dict:
        """
        Proporciona plantilla para análisis de estructura empresarial
        
        Args:
            company_name: Nombre de la empresa
        
        Returns:
            Dict con plantilla de análisis
        """
        print_banner(f"ANÁLISIS ESTRUCTURAL: {company_name}")
        
        template = {
            'company_name': company_name,
            'analysis_date': datetime.now().isoformat(),
            'basic_information': {
                'legal_name': 'Por verificar',
                'trade_name': company_name,
                'registration_number': 'Por verificar',
                'tax_id': 'Por verificar',
                'incorporation_date': 'Por verificar',
                'company_type': 'Por verificar (S.A., S.L., LLC, Inc., etc.)',
                'status': 'Por verificar (Activa, Disuelta, En liquidación)'
            },
            'contact_information': {
                'registered_address': 'Por verificar',
                'headquarters': 'Por verificar',
                'phone': 'Por verificar',
                'email': 'Por verificar',
                'website': 'Por verificar'
            },
            'corporate_structure': {
                'parent_company': 'Por verificar',
                'subsidiaries': [],
                'branches': [],
                'affiliated_companies': []
            },
            'key_personnel': {
                'directors': [],
                'officers': [],
                'registered_agent': 'Por verificar',
                'ultimate_beneficial_owners': []
            },
            'financial_information': {
                'revenue_range': 'Por verificar',
                'employee_count': 'Por verificar',
                'fiscal_year_end': 'Por verificar',
                'auditor': 'Por verificar'
            },
            'public_records': {
                'litigations': [],
                'liens': [],
                'bankruptcies': [],
                'regulatory_actions': []
            },
            'online_presence': {
                'websites': [],
                'social_media': {
                    'linkedin': None,
                    'twitter': None,
                    'facebook': None,
                    'instagram': None
                },
                'news_mentions': []
            },
            'verification_sources': [
                'OpenCorporates',
                'Registro mercantil/local',
                'LinkedIn Company',
                'Crunchbase',
                'Google News',
                'Wayback Machine'
            ]
        }
        
        print(f"{Colors.BOLD}PLANTILLA DE ANÁLISIS GENERADA{Colors.ENDC}")
        print(f"\nSe ha creado una plantilla con campos a verificar.")
        print(f"{Colors.WARNING}Nota:{Colors.ENDC} Esta herramienta no accede directamente a bases de datos privadas.")
        print(f"Los enlaces generados permiten verificar manualmente la información.")
        
        return template
    
    def verify_business_entity(self, entity_info: Dict) -> Dict:
        """
        Verifica la consistencia de información de entidad comercial
        
        Args:
            entity_info: Dict con información de la entidad
        
        Returns:
            Dict con análisis de consistencia
        """
        print_banner("VERIFICACIÓN DE ENTIDAD COMERCIAL")
        
        verification = {
            'input_data': entity_info,
            'consistency_checks': [],
            'red_flags': [],
            'verification_status': 'pending'
        }
        
        # Verificar campos requeridos
        required_fields = ['name', 'country', 'registration_number']
        missing_fields = [f for f in required_fields if not entity_info.get(f)]
        
        if missing_fields:
            verification['red_flags'].append({
                'type': 'incomplete_data',
                'description': f"Campos faltantes: {', '.join(missing_fields)}",
                'severity': 'medium'
            })
        
        # Verificar formato de número de registro según país
        country = entity_info.get('country', '').upper()
        reg_number = entity_info.get('registration_number', '')
        
        format_checks = {
            'US': r'^\d{2}-\d{7}$',  # EIN format
            'UK': r'^[A-Z]{2}\d{6}$',  # Companies House
            'ES': r'^[A-Z]\d{8}$',  # CIF español
            'MX': r'^[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}$',  # RFC mexicano
            'AR': r'^\d{2}-\d{8}-\d$'  # CUIT argentino
        }
        
        if country in format_checks and reg_number:
            pattern = format_checks[country]
            if not re.match(pattern, reg_number):
                verification['red_flags'].append({
                    'type': 'invalid_format',
                    'description': f"Formato de número de registro no coincide con estándar de {country}",
                    'expected_format': pattern,
                    'severity': 'high'
                })
        
        # Verificar consistencia de dirección
        if entity_info.get('address'):
            address = entity_info['address']
            if not any(char.isdigit() for char in address):
                verification['red_flags'].append({
                    'type': 'suspicious_address',
                    'description': 'La dirección no contiene números (posible dirección incompleta)',
                    'severity': 'low'
                })
        
        # Verificar dominio de email
        if entity_info.get('email'):
            email = entity_info['email']
            if '@gmail.com' in email.lower() or '@yahoo.com' in email.lower() or '@hotmail.com' in email.lower():
                verification['red_flags'].append({
                    'type': 'free_email_provider',
                    'description': 'Email de proveedor gratuito para empresa (poco profesional)',
                    'severity': 'low'
                })
        
        # Determinar estado de verificación
        high_risks = sum(1 for r in verification['red_flags'] if r['severity'] == 'high')
        if high_risks > 0:
            verification['verification_status'] = 'failed'
        elif verification['red_flags']:
            verification['verification_status'] = 'warning'
        else:
            verification['verification_status'] = 'passed'
        
        # Mostrar resultados
        print(f"{Colors.BOLD}RESULTADOS DE VERIFICACIÓN:{Colors.ENDC}")
        print(f"Estado: {verification['verification_status'].upper()}")
        
        if verification['red_flags']:
            print(f"\n{Colors.WARNING}BANDERAS ROJAS DETECTADAS:{Colors.ENDC}")
            for flag in verification['red_flags']:
                color = Colors.FAIL if flag['severity'] == 'high' else Colors.WARNING
                print(f"  {color}[{flag['severity'].upper()}]{Colors.ENDC} {flag['description']}")
        else:
            print_success("No se detectaron inconsistencias obvias")
        
        return verification
    
    def save_results(self, filename: str = None):
        """Guarda los resultados en JSON"""
        if not filename:
            company_safe = self.results.get('company_name', 'unknown').replace(' ', '_')
            filename = f"company_research_{company_safe}"
        return save_to_json(self.results, filename)


def main():
    """Función principal para uso en línea de comandos"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Herramienta de Investigación de Empresas OSINT',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python company_research.py -n "Acme Corporation"
  python company_research.py -n "Acme Corporation" --country US
  python company_research.py --structure "Empresa Ejemplo S.A."
  python company_research.py --verify entity_info.json
        """
    )
    
    parser.add_argument('-n', '--name', help='Nombre de la empresa a investigar')
    parser.add_argument('-c', '--country', help='Código de país (ISO 3166-1 alpha-2)')
    parser.add_argument('--structure', help='Generar plantilla de análisis estructural')
    parser.add_argument('--verify', help='Verificar información de entidad desde archivo JSON')
    parser.add_argument('--save', action='store_true', help='Guardar resultados en JSON')
    
    args = parser.parse_args()
    
    researcher = CompanyResearcher()
    
    if args.name:
        results = researcher.search_company(args.name, args.country)
        if args.save:
            researcher.save_results()
    
    elif args.structure:
        template = researcher.analyze_company_structure(args.structure)
        if args.save:
            save_to_json(template, f"company_structure_{args.structure.replace(' ', '_')}")
    
    elif args.verify:
        try:
            with open(args.verify, 'r') as f:
                entity_info = json.load(f)
            verification = researcher.verify_business_entity(entity_info)
            if args.save:
                save_to_json(verification, "entity_verification")
        except FileNotFoundError:
            print_error(f"Archivo no encontrado: {args.verify}")
        except json.JSONDecodeError:
            print_error(f"Archivo JSON inválido: {args.verify}")
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
