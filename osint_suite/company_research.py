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
        recommendations.extend([\n            'Buscar dominios web asociados (whois history)',\n            'Verificar presencia en redes sociales corporativas',\n            'Buscar en Wayback Machine para versiones históricas de web',\n            'Revisar Glassdoor/Indeed para información de empleados'\n        ])
        
        return recommendations
    
    def analyze_company_structure(self, company_name: str) -> Dict:\n        \"\"\"\n        Proporciona plantilla para análisis de estructura empresarial\n        \n        Args:\n            company_name: Nombre de la empresa\n        \n        Returns:\n            Dict con plantilla de análisis\n        \"\"\"\n        print_banner(f\"ANÁLISIS ESTRUCTURAL: {company_name}\")\n        \n        template = {\n            'company_name': company_name,\n            'analysis_date': datetime.now().isoformat(),\n            'basic_information': {\n                'legal_name': 'Por verificar',\n                'trade_name': company_name,\n                'registration_number': 'Por verificar',\n                'tax_id': 'Por verificar',\n                'incorporation_date': 'Por verificar',\n                'company_type': 'Por verificar (S.A., S.L., LLC, Inc., etc.)',\n                'status': 'Por verificar (Activa, Disuelta, En liquidación)'\n            },\n            'contact_information': {\n                'registered_address': 'Por verificar',\n                'headquarters': 'Por verificar',\n                'phone': 'Por verificar',\n                'email': 'Por verificar',\n                'website': 'Por verificar'\n            },\n            'corporate_structure': {\n                'parent_company': 'Por verificar',\n                'subsidiaries': [],\n                'branches': [],\n                'affiliated_companies': []\n            },\n            'key_personnel': {\n                'directors': [],\n                'officers': [],\n                'registered_agent': 'Por verificar',\n                'ultimate_beneficial_owners': []\n            },\n            'financial_information': {\n                'revenue_range': 'Por verificar',\n                'employee_count': 'Por verificar',\n                'fiscal_year_end': 'Por verificar',\n                'auditor': 'Por verificar'\n            },\n            'public_records': {\n                'litigations': [],\n                'liens': [],\n                'bankruptcies': [],\n                'regulatory_actions': []\n            },\n            'online_presence': {\n                'websites': [],\n                'social_media': {\n                    'linkedin': None,\n                    'twitter': None,\n                    'facebook': None,\n                    'instagram': None\n                },\n                'news_mentions': []\n            },\n            'verification_sources': [\n                'OpenCorporates',\n                'Registro mercantil/local',\n                'LinkedIn Company',\n                'Crunchbase',\n                'Google News',\n                'Wayback Machine'\n            ]\n        }\n        \n        print(f\"{Colors.BOLD}PLANTILLA DE ANÁLISIS GENERADA{Colors.ENDC}\")\n        print(f\"\\nSe ha creado una plantilla con campos a verificar.\")\n        print(f\"{Colors.WARNING}Nota:{Colors.ENDC} Esta herramienta no accede directamente a bases de datos privadas.\")\n        print(f\"Los enlaces generados permiten verificar manualmente la información.\")\n        \n        return template
    
    def verify_business_entity(self, entity_info: Dict) -> Dict:
n        \"\"\"\n        Verifica la consistencia de información de entidad comercial\n        \n        Args:
            entity_info: Dict con información de la entidad
        
        Returns:
n            Dict con análisis de consistencia
        \"\"\"\n        print_banner(\"VERIFICACIÓN DE ENTIDAD COMERCIAL\")\n        \n        verification = {\n            'input_data': entity_info,\n            'consistency_checks': [],\n            'red_flags': [],\n            'verification_status': 'pending'\n        }\n        \n        # Verificar campos requeridos\n        required_fields = ['name', 'country', 'registration_number']\n        missing_fields = [f for f in required_fields if not entity_info.get(f)]\n        \n        if missing_fields:\n            verification['red_flags'].append({\n                'type': 'incomplete_data',\n                'description': f'Campos faltantes: {\", \".join(missing_fields)}',\n                'severity': 'medium'\n            })\n        \n        # Verificar formato de número de registro según país\n        country = entity_info.get('country', '').upper()\n        reg_number = entity_info.get('registration_number', '')\n        \n        format_checks = {\n            'US': r'^\\d{2}-\\d{7}$',  # EIN format\n            'UK': r'^[A-Z]{2}\\d{6}$',  # Companies House\n            'ES': r'^[A-Z]\\d{8}$',  # CIF español\n            'MX': r'^[A-Z&Ñ]{3,4}\\d{6}[A-Z0-9]{3}$',  # RFC mexicano\n            'AR': r'^\\d{2}-\\d{8}-\\d$'  # CUIT argentino\n        }\n        \n        if country in format_checks and reg_number:\n            pattern = format_checks[country]\n            if not re.match(pattern, reg_number):\n                verification['red_flags'].append({\n                    'type': 'invalid_format',\n                    'description': f'Formato de número de registro no coincide con estándar de {country}',\n                    'expected_format': pattern,\n                    'severity': 'high'\n                })\n        \n        # Verificar consistencia de dirección\n        if entity_info.get('address'):\n            address = entity_info['address']\n            if not any(char.isdigit() for char in address):\n                verification['red_flags'].append({\n                    'type': 'suspicious_address',\n                    'description': 'La dirección no contiene números (posible dirección incompleta)',\n                    'severity': 'low'\n                })\n        \n        # Verificar dominio de email\n        if entity_info.get('email'):\n            email = entity_info['email']\n            if '@gmail.com' in email.lower() or '@yahoo.com' in email.lower() or '@hotmail.com' in email.lower():\n                verification['red_flags'].append({\n                    'type': 'free_email_provider',\n                    'description': 'Email de proveedor gratuito para empresa (poco profesional)',\n                    'severity': 'low'\n                })\n        \n        # Determinar estado de verificación\n        high_risks = sum(1 for r in verification['red_flags'] if r['severity'] == 'high')\n        if high_risks > 0:\n            verification['verification_status'] = 'failed'\n        elif verification['red_flags']:\n            verification['verification_status'] = 'warning'\n        else:\n            verification['verification_status'] = 'passed'\n        \n        # Mostrar resultados\n        print(f\"{Colors.BOLD}RESULTADOS DE VERIFICACIÓN:{Colors.ENDC}\")\n        print(f\"Estado: {verification['verification_status'].upper()}\")\n        \n        if verification['red_flags']:\n            print(f\"\\n{Colors.WARNING}BANDERAS ROJAS DETECTADAS:{Colors.ENDC}\")\n            for flag in verification['red_flags']:\n                color = Colors.FAIL if flag['severity'] == 'high' else Colors.WARNING\n                print(f\"  {color}[{flag['severity'].upper()}]{Colors.ENDC} {flag['description']}\")\n        else:\n            print_success(\"No se detectaron inconsistencias obvias\")\n        \n        return verification
    
    def save_results(self, filename: str = None):
n        \"\"\"Guarda los resultados en JSON\"\"\"\n        if not filename:\n            company_safe = self.results.get('company_name', 'unknown').replace(' ', '_')\n            filename = f\"company_research_{company_safe}\"\n        return save_to_json(self.results, filename)\n\n\ndef main():\n    \"\"\"Función principal para uso en línea de comandos\"\"\"\n    import argparse\n    \n    parser = argparse.ArgumentParser(\n        description='Herramienta de Investigación de Empresas OSINT',\n        formatter_class=argparse.RawDescriptionHelpFormatter,\n        epilog=\"\"\"\nEjemplos:\n  python company_research.py -n \"Acme Corporation\"\n  python company_research.py -n \"Acme Corporation\" --country US\n  python company_research.py --structure \"Empresa Ejemplo S.A.\"\n  python company_research.py --verify entity_info.json\n        \"\"\"\n    )\n    \n    parser.add_argument('-n', '--name', help='Nombre de la empresa a investigar')\n    parser.add_argument('-c', '--country', help='Código de país (ISO 3166-1 alpha-2)')\n    parser.add_argument('--structure', help='Generar plantilla de análisis estructural')\n    parser.add_argument('--verify', help='Verificar información de entidad desde archivo JSON')\n    parser.add_argument('--save', action='store_true', help='Guardar resultados en JSON')\n    \n    args = parser.parse_args()\n    \n    researcher = CompanyResearcher()\n    \n    if args.name:\n        results = researcher.search_company(args.name, args.country)\n        if args.save:\n            researcher.save_results()\n    \n    elif args.structure:\n        template = researcher.analyze_company_structure(args.structure)\n        if args.save:\n            save_to_json(template, f\"company_structure_{args.structure.replace(' ', '_')}\")\n    \n    elif args.verify:\n        try:\n            with open(args.verify, 'r') as f:\n                entity_info = json.load(f)\n            verification = researcher.verify_business_entity(entity_info)\n            if args.save:\n                save_to_json(verification, \"entity_verification\")\n        except FileNotFoundError:\n            print_error(f\"Archivo no encontrado: {args.verify}\")\n        except json.JSONDecodeError:\n            print_error(f\"Archivo JSON inválido: {args.verify}\")\n    \n    else:\n        parser.print_help()\n\n\nif __name__ == '__main__':\n    main()\n
