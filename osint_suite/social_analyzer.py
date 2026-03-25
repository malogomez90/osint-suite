"""
Analizador de Redes Sociales - Análisis de perfiles de Instagram, Twitter, etc.
Excluye: Scraping agresivo, automatización de interacciones, bypass de rate limits
"""

import re
import json
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime
from bs4 import BeautifulSoup
from .utils import (
    Colors, print_banner, print_success, print_error, 
    print_warning, print_info, make_request, save_to_json,
    extract_urls, format_timestamp
)


class SocialMediaAnalyzer:
    """Analizador de perfiles de redes sociales"""
    
    def __init__(self, delay: float = 2.0):
        self.delay = delay
        self.results = {}
    
    def analyze_instagram(self, username: str) -> Dict:
        """
        Analiza un perfil de Instagram (usando métodos no intrusivos)
        
        Args:
            username: Nombre de usuario de Instagram
        
        Returns:
            Dict con información del perfil
        """
        print_info(f"Analizando perfil de Instagram: @{username}")
        
        result = {
            'platform': 'Instagram',
            'username': username,
            'profile_url': f'https://www.instagram.com/{username}/',
            'available': False,
            'error': None,
            'metadata': {}
        }
        
        try:
            # Petición básica para verificar existencia
            url = f'https://www.instagram.com/{username}/'
            response = make_request(url, timeout=10)
            
            if response is None:
                result['error'] = 'No se pudo conectar'
                return result
            
            if response.status_code == 200:
                result['available'] = True
                
                # Extraer información básica del HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Buscar meta tags
                meta_title = soup.find('meta', property='og:title')
                meta_description = soup.find('meta', property='og:description')
                meta_image = soup.find('meta', property='og:image')
                
                if meta_title:
                    result['metadata']['title'] = meta_title.get('content', '')
                
                if meta_description:
                    desc = meta_description.get('content', '')
                    result['metadata']['description'] = desc
                    
                    # Intentar extraer estadísticas básicas de la descripción
                    # Instagram típicamente muestra: "X followers, Y following, Z posts"
                    followers_match = re.search(r'([\\d,]+)\\s+followers?', desc, re.IGNORECASE)
                    if followers_match:
                        result['metadata']['followers_text'] = followers_match.group(1)
                    
                    following_match = re.search(r'([\\d,]+)\\s+following?', desc, re.IGNORECASE)
                    if following_match:
                        result['metadata']['following_text'] = following_match.group(1)
                    
                    posts_match = re.search(r'([\\d,]+)\\s+posts?', desc, re.IGNORECASE)
                    if posts_match:
                        result['metadata']['posts_text'] = posts_match.group(1)
                
                if meta_image:
                    result['metadata']['profile_image'] = meta_image.get('content', '')
                
                # Buscar enlaces en la página
                result['metadata']['external_links'] = self._extract_profile_links(soup)
                
                print_success(f"Peril encontrado: @{username}")
                if result['metadata'].get('description'):
                    print(f"  Bio: {result['metadata']['description'][:100]}...")
                
            elif response.status_code == 404:
                result['error'] = 'Perfil no encontrado o no existe'
                print_error(result['error'])
            else:
                result['error'] = f'Error HTTP {response.status_code}'
                print_error(result['error'])
                
        except Exception as e:
            result['error'] = f'Error: {str(e)}'
            print_error(result['error'])
        
        return result
    
    def analyze_twitter(self, username: str) -> Dict:
        """
        Analiza un perfil de Twitter/X (usando Nitter como alternativa)
        
        Args:
            username: Nombre de usuario de Twitter
        
        Returns:
            Dict con información del perfil
        """
        print_info(f"Analizando perfil de Twitter: @{username}")
        
        result = {
            'platform': 'Twitter/X',
            'username': username,
            'profile_url': f'https://twitter.com/{username}',
            'available': False,
            'error': None,
            'metadata': {}
        }
        
        try:
            # Usar Nitter (instancia alternativa) para evitar restricciones
            nitter_instances = [
                f'https://nitter.net/{username}',
                f'https://nitter.it/{username}',
                f'https://nitter.cz/{username}'
            ]
            
            for url in nitter_instances:
                try:
                    response = make_request(url, timeout=10)
                    if response and response.status_code == 200:
                        result['available'] = True
                        
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # Extraer información del perfil
                        profile_card = soup.find('div', class_='profile-card')
                        if profile_card:
                            # Nombre completo
                            fullname = profile_card.find('a', class_='profile-card-fullname')
                            if fullname:
                                result['metadata']['full_name'] = fullname.get_text(strip=True)
                            
                            # Bio
                            bio = profile_card.find('div', class_='profile-bio')
                            if bio:
                                result['metadata']['bio'] = bio.get_text(strip=True)
                            
                            # Estadísticas
                            stats = profile_card.find_all('div', class_='profile-stat-num')
                            if len(stats) >= 3:
                                result['metadata']['tweets_count'] = stats[0].get_text(strip=True)
                                result['metadata']['following_count'] = stats[1].get_text(strip=True)
                                result['metadata']['followers_count'] = stats[2].get_text(strip=True)
                        
                        # Ubicación
                        location = soup.find('div', class_='profile-location')
                        if location:
                            result['metadata']['location'] = location.get_text(strip=True)
                        
                        # Website
                        website = soup.find('div', class_='profile-website')
                        if website:
                            link = website.find('a')
                            if link:
                                result['metadata']['website'] = link.get('href', '')
                        
                        print_success(f"Perfil encontrado: @{username}")
                        if result['metadata'].get('full_name'):
                            print(f"  Nombre: {result['metadata']['full_name']}")
                        if result['metadata'].get('bio'):
                            print(f"  Bio: {result['metadata']['bio'][:100]}...")
                        
                        break  # Salir del loop si tuvimos éxito
                        
                except Exception as e:
                    continue  # Intentar con siguiente instancia
            
            if not result['available']:
                result['error'] = 'No se pudo acceder al perfil'
                print_error(result['error'])
                
        except Exception as e:
            result['error'] = f'Error: {str(e)}'
            print_error(result['error'])
        
        return result
    
    def analyze_reddit(self, username: str) -> Dict:
        """
        Analiza un perfil de Reddit
        
        Args:
            username: Nombre de usuario de Reddit
        
        Returns:
            Dict con información del perfil
        """
        print_info(f"Analizando perfil de Reddit: u/{username}")
        
        result = {
            'platform': 'Reddit',
            'username': username,
            'profile_url': f'https://www.reddit.com/user/{username}/',
            'available': False,
            'error': None,
            'metadata': {}
        }
        
        try:
            # Usar JSON endpoint de Reddit
            url = f'https://www.reddit.com/user/{username}/about.json'
            headers = {
                'User-Agent': 'OSINT-Research-Tool/1.0'
            }
            
            response = make_request(url, headers=headers, timeout=10)
            
            if response and response.status_code == 200:
                data = response.json()
                
                if 'data' in data:
                    user_data = data['data']
                    result['available'] = True
                    
                    result['metadata'] = {
                        'name': user_data.get('name'),
                        'created_utc': user_data.get('created_utc'),
                        'link_karma': user_data.get('link_karma'),
                        'comment_karma': user_data.get('comment_karma'),
                        'is_gold': user_data.get('is_gold'),
                        'is_mod': user_data.get('is_mod'),
                        'is_employee': user_data.get('is_employee'),
                        'verified': user_data.get('verified'),
                        'has_verified_email': user_data.get('has_verified_email'),
                        'icon_img': user_data.get('icon_img'),
                        'subreddit': user_data.get('subreddit')
                    }
                    
                    # Convertir timestamp
                    if result['metadata']['created_utc']:
                        created_date = datetime.fromtimestamp(result['metadata']['created_utc'])
                        result['metadata']['created_date'] = created_date.strftime('%Y-%m-%d')
                    
                    print_success(f"Perfil encontrado: u/{username}")
                    print(f"  Karma: {result['metadata']['link_karma']} (links) / {result['metadata']['comment_karma']} (comments)")
                    if result['metadata'].get('created_date'):
                        print(f"  Cuenta creada: {result['metadata']['created_date']}")
                    
                else:
                    result['error'] = 'Usuario no encontrado'
                    print_error(result['error'])
                    
            elif response and response.status_code == 404:
                result['error'] = 'Usuario no encontrado'
                print_error(result['error'])
            else:
                result['error'] = f'Error HTTP {response.status_code if response else "No response"}'
                print_error(result['error'])
                
        except Exception as e:
            result['error'] = f'Error: {str(e)}'
            print_error(result['error'])
        
        return result
    
    def analyze_github(self, username: str) -> Dict:
        """
        Analiza un perfil de GitHub
        
        Args:
            username: Nombre de usuario de GitHub
        
        Returns:
            Dict con información del perfil
        """
        print_info(f"Analizando perfil de GitHub: @{username}")
        
        result = {
            'platform': 'GitHub',
            'username': username,
            'profile_url': f'https://github.com/{username}',
            'available': False,
            'error': None,
            'metadata': {}
        }
        
        try:
            # Usar API de GitHub (pública, rate limitada)
            url = f'https://api.github.com/users/{username}'
            response = make_request(url, timeout=10)
            
            if response and response.status_code == 200:
                user_data = response.json()
                result['available'] = True
                
                result['metadata'] = {
                    'login': user_data.get('login'),
                    'id': user_data.get('id'),
                    'node_id': user_data.get('node_id'),
                    'avatar_url': user_data.get('avatar_url'),
                    'html_url': user_data.get('html_url'),
                    'type': user_data.get('type'),
                    'site_admin': user_data.get('site_admin'),
                    'name': user_data.get('name'),
                    'company': user_data.get('company'),
                    'blog': user_data.get('blog'),
                    'location': user_data.get('location'),
                    'email': user_data.get('email'),
                    'hireable': user_data.get('hireable'),
                    'bio': user_data.get('bio'),
                    'twitter_username': user_data.get('twitter_username'),
                    'public_repos': user_data.get('public_repos'),
                    'public_gists': user_data.get('public_gists'),
                    'followers': user_data.get('followers'),
                    'following': user_data.get('following'),
                    'created_at': user_data.get('created_at'),
                    'updated_at': user_data.get('updated_at')
                }
                
                print_success(f"Perfil encontrado: @{username}")
                if result['metadata'].get('name'):
                    print(f"  Nombre: {result['metadata']['name']}")
                if result['metadata'].get('bio'):
                    print(f"  Bio: {result['metadata']['bio'][:100]}...")
                print(f"  Repos públicos: {result['metadata']['public_repos']}")
                print(f"  Seguidores: {result['metadata']['followers']}")
                
            elif response and response.status_code == 404:
                result['error'] = 'Usuario no encontrado'
                print_error(result['error'])
            else:
                result['error'] = f'Error HTTP {response.status_code if response else "No response"}'
                print_error(result['error'])
                
        except Exception as e:
            result['error'] = f'Error: {str(e)}'
            print_error(result['error'])
        
        return result
    
    def _extract_profile_links(self, soup: BeautifulSoup) -> List[str]:
        """Extrae enlaces externos del perfil"""
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith('http') and 'instagram.com' not in href:
                links.append(href)
        return list(set(links))[:10]  # Limitar a 10 enlaces únicos
    
    def cross_reference(self, username: str, platforms: List[str] = None) -> Dict:
        """
        Analiza un nombre de usuario en múltiples plataformas
        
        Args:
            username: Nombre de usuario
            platforms: Lista de plataformas a analizar
        
        Returns:
            Dict con resultados de todas las plataformas
        """
        if platforms is None:
            platforms = ['instagram', 'twitter', 'reddit', 'github']
        
        print_banner(f"ANÁLISIS CROSS-PLATFORM: @{username}")
        
        results = {
            'username': username,
            'platforms_checked': platforms,
            'profiles_found': [],
            'profiles_not_found': [],
            'cross_references': []
        }
        
        for platform in platforms:
            print(f"\n{Colors.BOLD}Verificando {platform}...{Colors.ENDC}")
            
            if platform.lower() == 'instagram':
                result = self.analyze_instagram(username)
            elif platform.lower() in ['twitter', 'x']:
                result = self.analyze_twitter(username)
            elif platform.lower() == 'reddit':
                result = self.analyze_reddit(username)
            elif platform.lower() == 'github':
                result = self.analyze_github(username)
            else:
                print_warning(f"Plataforma '{platform}' no soportada")
                continue
            
            if result['available']:
                results['profiles_found'].append(result)
            else:
                results['profiles_not_found'].append(result)
        
        # Buscar cross-references
        print(f"\n{Colors.BOLD}BUSCANDO CROSS-REFERENCES...{Colors.ENDC}")
        
        all_links = []
        for profile in results['profiles_found']:
            meta = profile.get('metadata', {})
            
            # Buscar enlaces a otras redes
            if meta.get('website'):
                all_links.append(meta['website'])
            if meta.get('external_links'):
                all_links.extend(meta['external_links'])
            if meta.get('blog'):
                all_links.append(meta['blog'])
            if meta.get('twitter_username'):
                results['cross_references'].append({
                    'from': profile['platform'],
                    'to': 'Twitter',
                    'username': meta['twitter_username']
                })
        
        # Analizar enlaces encontrados
        for link in all_links:
            for platform in ['twitter', 'instagram', 'github', 'linkedin']:
                if platform in link.lower():
                    results['cross_references'].append({
                        'type': 'link',
                        'url': link,
                        'platform': platform
                    })
        
        # Resumen
        print(f"\n{Colors.BOLD}RESUMEN CROSS-PLATFORM:{Colors.ENDC}")
        print(f"  Perfiles encontrados: {len(results['profiles_found'])}")
        print(f"  No encontrados: {len(results['profiles_not_found'])}")
        print(f"  Cross-references: {len(results['cross_references'])}")
        
        if results['cross_references']:
            print(f"\n{Colors.OKCYAN}Referencias cruzadas detectadas:{Colors.ENDC}")
            for ref in results['cross_references']:
                print(f"  • {ref.get('from', 'Unknown')} -> {ref.get('to', ref.get('platform', 'Unknown'))}: {ref.get('username', ref.get('url', 'N/A'))}")
        
        self.results = results
        return results
    
    def save_results(self, filename: str = None):
        """Guarda los resultados en JSON"""
        if not filename:
            filename = f"social_analysis_{self.results.get('username', 'unknown')}"
        return save_to_json(self.results, filename)


def main():
    """Función principal para uso en línea de comandos"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Analizador de Redes Sociales OSINT',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python social_analyzer.py -u johndoe --cross-reference
  python social_analyzer.py -u johndoe -p instagram twitter github
  python social_analyzer.py -u johndoe --instagram --save
        """
    )
    
    parser.add_argument('-u', '--username', required=True, help='Nombre de usuario a analizar')
    parser.add_argument('-p', '--platforms', nargs='+', 
                       choices=['instagram', 'twitter', 'reddit', 'github'],
                       help='Plataformas específicas a analizar')
    parser.add_argument('--cross-reference', action='store_true',
                       help='Análisis cross-platform automático')
    parser.add_argument('--instagram', action='store_true', help='Analizar solo Instagram')
    parser.add_argument('--twitter', action='store_true', help='Analizar solo Twitter')
    parser.add_argument('--reddit', action='store_true', help='Analizar solo Reddit')
    parser.add_argument('--github', action='store_true', help='Analizar solo GitHub')
    parser.add_argument('--save', action='store_true', help='Guardar resultados en JSON')
    
    args = parser.parse_args()
    
    analyzer = SocialMediaAnalyzer()
    
    if args.cross_reference:
        results = analyzer.cross_reference(args.username, args.platforms)
    else:
        # Análisis individual según flags
        platforms = []
        if args.instagram:
            platforms.append('instagram')
        if args.twitter:
            platforms.append('twitter')
        if args.reddit:
            platforms.append('reddit')
        if args.github:
            platforms.append('github')
        
        if not platforms:
            # Si no se especificó ninguna, hacer cross-reference completo
            results = analyzer.cross_reference(args.username)
        else:
            results = analyzer.cross_reference(args.username, platforms)
    
    if args.save:
        analyzer.save_results()


if __name__ == '__main__':
    main()
