"""
Buscador de Usuarios - Verifica nombres de usuario en múltiples plataformas
Excluye: APIs que requieran autenticación compleja o scraping agresivo
"""

import requests
import time
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from .utils import (
    Colors, print_banner, print_success, print_error, 
    print_warning, print_info, clean_username, make_request, save_to_json
)


class UsernameSearcher:
    """Buscador de nombres de usuario en múltiples plataformas"""
    
    def __init__(self, delay: float = 1.0):
        self.delay = delay
        self.results = {}
        
        # Plataformas que se pueden verificar sin autenticación
        self.platforms = {
            'GitHub': {
                'url': 'https://github.com/{}',
                'check': lambda r: r.status_code == 200 and 'Not Found' not in r.text,
                'profile_url': 'https://github.com/{}'
            },
            'Twitter/X': {
                'url': 'https://nitter.net/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://twitter.com/{}'
            },
            'Instagram': {
                'url': 'https://www.instagram.com/{}/',
                'check': lambda r: r.status_code == 200 and 'Page Not Found' not in r.text,
                'profile_url': 'https://www.instagram.com/{}/'
            },
            'Reddit': {
                'url': 'https://www.reddit.com/user/{}',
                'check': lambda r: r.status_code == 200 and 'Sorry' not in r.text,
                'profile_url': 'https://www.reddit.com/user/{}'
            },
            'YouTube': {
                'url': 'https://www.youtube.com/@{}',
                'check': lambda r: r.status_code == 200 and 'no se ha encontrado' not in r.text.lower(),
                'profile_url': 'https://www.youtube.com/@{}'
            },
            'TikTok': {
                'url': 'https://www.tiktok.com/@{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://www.tiktok.com/@{}'
            },
            'Pinterest': {
                'url': 'https://www.pinterest.com/{}/',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://www.pinterest.com/{}/'
            },
            'LinkedIn': {
                'url': 'https://www.linkedin.com/in/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://www.linkedin.com/in/{}'
            },
            'Medium': {
                'url': 'https://medium.com/@{}',
                'check': lambda r: r.status_code == 200 and '404' not in r.text,
                'profile_url': 'https://medium.com/@{}'
            },
            'Dev.to': {
                'url': 'https://dev.to/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://dev.to/{}'
            },
            'Stack Overflow': {
                'url': 'https://stackoverflow.com/users/{}',
                'check': lambda r: r.status_code == 200 and 'Page Not Found' not in r.text,
                'profile_url': 'https://stackoverflow.com/users/{}'
            },
            'GitLab': {
                'url': 'https://gitlab.com/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://gitlab.com/{}'
            },
            'Bitbucket': {
                'url': 'https://bitbucket.org/{}/',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://bitbucket.org/{}/'
            },
            'CodePen': {
                'url': 'https://codepen.io/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://codepen.io/{}'
            },
            'Dribbble': {
                'url': 'https://dribbble.com/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://dribbble.com/{}'
            },
            'Behance': {
                'url': 'https://www.behance.net/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://www.behance.net/{}'
            },
            'Flickr': {
                'url': 'https://www.flickr.com/people/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://www.flickr.com/people/{}'
            },
            'Vimeo': {
                'url': 'https://vimeo.com/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://vimeo.com/{}'
            },
            'SoundCloud': {
                'url': 'https://soundcloud.com/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://soundcloud.com/{}'
            },
            'Spotify': {
                'url': 'https://open.spotify.com/user/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://open.spotify.com/user/{}'
            },
            'Goodreads': {
                'url': 'https://www.goodreads.com/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://www.goodreads.com/{}'
            },
            'Wattpad': {
                'url': 'https://www.wattpad.com/user/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://www.wattpad.com/user/{}'
            },
            'Quora': {
                'url': 'https://www.quora.com/profile/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://www.quora.com/profile/{}'
            },
            'Twitch': {
                'url': 'https://www.twitch.tv/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://www.twitch.tv/{}'
            },
            'Steam': {
                'url': 'https://steamcommunity.com/id/{}',
                'check': lambda r: r.status_code == 200 and 'The specified profile could not be found' not in r.text,
                'profile_url': 'https://steamcommunity.com/id/{}'
            },
            'Keybase': {
                'url': 'https://keybase.io/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://keybase.io/{}'
            },
            'About.me': {
                'url': 'https://about.me/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://about.me/{}'
            },
            'Gravatar': {
                'url': 'https://en.gravatar.com/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://en.gravatar.com/{}'
            },
            'Pastebin': {
                'url': 'https://pastebin.com/u/{}',
                'check': lambda r: r.status_code == 200 and 'Not Found' not in r.text,
                'profile_url': 'https://pastebin.com/u/{}'
            },
            'HackerNews': {
                'url': 'https://news.ycombinator.com/user?id={}',
                'check': lambda r: r.status_code == 200 and 'No such user' not in r.text,
                'profile_url': 'https://news.ycombinator.com/user?id={}'
            },
            'ProductHunt': {
                'url': 'https://www.producthunt.com/@{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://www.producthunt.com/@{}'
            },
            'SlideShare': {
                'url': 'https://www.slideshare.net/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://www.slideshare.net/{}'
            },
            'Scribd': {
                'url': 'https://www.scribd.com/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://www.scribd.com/{}'
            },
            'Badoo': {
                'url': 'https://badoo.com/profile/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://badoo.com/profile/{}'
            },
            'Bandcamp': {
                'url': 'https://{}.bandcamp.com',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://{}.bandcamp.com'
            },
            'Blogger': {
                'url': 'https://{}.blogspot.com',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://{}.blogspot.com'
            },
            'WordPress.com': {
                'url': 'https://{}.wordpress.com',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://{}.wordpress.com'
            },
            'Imgur': {
                'url': 'https://imgur.com/user/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://imgur.com/user/{}'
            },
            'Kaggle': {
                'url': 'https://www.kaggle.com/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://www.kaggle.com/{}'
            },
            'Launchpad': {
                'url': 'https://launchpad.net/~{}',
                'check': lambda r: r.status_code == 200 and 'NotFound' not in r.text,
                'profile_url': 'https://launchpad.net/~{}'
            },
            'SourceForge': {
                'url': 'https://sourceforge.net/u/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://sourceforge.net/u/{}'
            },
            'MySpace': {
                'url': 'https://myspace.com/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://myspace.com/{}'
            },
            'Newgrounds': {
                'url': 'https://{}.newgrounds.com',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://{}.newgrounds.com'
            },
            'Roblox': {
                'url': 'https://www.roblox.com/user.aspx?username={}',
                'check': lambda r: r.status_code == 200 and 'User does not exist' not in r.text,
                'profile_url': 'https://www.roblox.com/user.aspx?username={}'
            },
            'Snapchat': {
                'url': 'https://www.snapchat.com/add/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://www.snapchat.com/add/{}'
            },
            'Telegram': {
                'url': 'https://t.me/{}',
                'check': lambda r: r.status_code == 200 and 'tgme_page_title' in r.text,
                'profile_url': 'https://t.me/{}'
            },
            'TripAdvisor': {
                'url': 'https://www.tripadvisor.com/members/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://www.tripadvisor.com/members/{}'
            },
            'VSCO': {
                'url': 'https://vsco.co/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://vsco.co/{}'
            },
            'Wikipedia': {
                'url': 'https://en.wikipedia.org/wiki/User:{}',
                'check': lambda r: r.status_code == 200 and 'does not exist' not in r.text,
                'profile_url': 'https://en.wikipedia.org/wiki/User:{}'
            },
            'Xing': {
                'url': 'https://www.xing.com/profile/{}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://www.xing.com/profile/{}'
            },
            'Yelp': {
                'url': 'https://www.yelp.com/user_details?userid={}',
                'check': lambda r: r.status_code == 200,
                'profile_url': 'https://www.yelp.com/user_details?userid={}'
            }
        }
    
    def check_platform(self, username: str, platform: str, info: Dict) -> Dict:
        """Verifica un nombre de usuario en una plataforma específica"""
        url = info['url'].format(username)
        
        try:
            response = make_request(url, timeout=5)
            
            if response is None:
                return {
                    'platform': platform,
                    'url': url,
                    'exists': False,
                    'status': 'Error de conexión',
                    'profile_url': info['profile_url'].format(username)
                }
            
            exists = info['check'](response)
            
            return {
                'platform': platform,
                'url': url,
                'exists': exists,
                'status_code': response.status_code,
                'profile_url': info['profile_url'].format(username)
            }
            
        except Exception as e:
            return {
                'platform': platform,
                'url': url,
                'exists': False,
                'status': f'Error: {str(e)}',
                'profile_url': info['profile_url'].format(username)
            }
    
    def search(self, username: str, platforms: List[str] = None, max_workers: int = 5) -> Dict:
        """
        Busca un nombre de usuario en múltiples plataformas
        
        Args:
            username: Nombre de usuario a buscar
            platforms: Lista de plataformas específicas (None = todas)
            max_workers: Número máximo de hilos concurrentes
        
        Returns:
            Dict con los resultados de la búsqueda
        """
        username = clean_username(username)
        
        print_banner(f"Buscando usuario: @{username}")
        print_info(f"Plataformas a verificar: {len(platforms) if platforms else len(self.platforms)}")
        print()
        
        # Seleccionar plataformas
        platforms_to_check = {}
        if platforms:
            for p in platforms:
                if p in self.platforms:
                    platforms_to_check[p] = self.platforms[p]
                else:
                    print_warning(f"Plataforma '{p}' no disponible")
        else:
            platforms_to_check = self.platforms
        
        results = {
            'username': username,
            'total_checked': len(platforms_to_check),
            'found': [],
            'not_found': [],
            'errors': []
        }
        
        # Verificación concurrente
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_platform = {
                executor.submit(self.check_platform, username, platform, info): platform 
                for platform, info in platforms_to_check.items()
            }
            
            for future in as_completed(future_to_platform):
                platform = future_to_platform[future]
                try:
                    result = future.result()
                    
                    if result['exists']:
                        results['found'].append(result)
                        print_success(f"[{platform}] Perfil encontrado: {result['profile_url']}")
                    else:
                        results['not_found'].append(result)
                        print_error(f"[{platform}] No encontrado")
                        
                except Exception as e:
                    error_result = {
                        'platform': platform,
                        'error': str(e)
                    }
                    results['errors'].append(error_result)
                    print_error(f"[{platform}] Error: {str(e)}")
                
                time.sleep(self.delay / max_workers)  # Rate limiting
        
        # Resumen
        print()
        print_banner("RESUMEN DE BÚSQUEDA")
        print(f"{Colors.BOLD}Usuario:{Colors.ENDC} @{username}")
        print(f"{Colors.BOLD}Total verificado:{Colors.ENDC} {results['total_checked']}")
        print(f"{Colors.OKGREEN}{Colors.BOLD}Perfiles encontrados:{Colors.ENDC} {len(results['found'])}")
        print(f"{Colors.FAIL}{Colors.BOLD}No encontrados:{Colors.ENDC} {len(results['not_found'])}")
        print(f"{Colors.WARNING}{Colors.BOLD}Errores:{Colors.ENDC} {len(results['errors'])}")
        print()
        
        if results['found']:
            print(f"{Colors.OKGREEN}{Colors.BOLD}Perfiles encontrados:{Colors.ENDC}")
            for profile in results['found']:
                print(f"  • {profile['platform']}: {profile['profile_url']}")
        
        self.results = results
        return results
    
    def save_results(self, filename: str = None):
        """Guarda los resultados en JSON"""
        if not filename:
            filename = f"username_search_{self.results.get('username', 'unknown')}"
        return save_to_json(self.results, filename)


def main():
    """Función principal para uso en línea de comandos"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Buscador de nombres de usuario en múltiples plataformas',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python username_search.py -u johndoe
  python username_search.py -u johndoe -p GitHub Twitter Instagram
  python username_search.py -u johndoe --save
        """
    )
    
    parser.add_argument('-u', '--username', required=True, help='Nombre de usuario a buscar')
    parser.add_argument('-p', '--platforms', nargs='+', help='Plataformas específicas a verificar')
    parser.add_argument('--save', action='store_true', help='Guardar resultados en JSON')
    parser.add_argument('--delay', type=float, default=1.0, help='Delay entre peticiones (segundos)')
    parser.add_argument('--workers', type=int, default=5, help='Número de workers concurrentes')
    
    args = parser.parse_args()
    
    searcher = UsernameSearcher(delay=args.delay)
    results = searcher.search(args.username, args.platforms, args.workers)
    
    if args.save:
        searcher.save_results()


if __name__ == '__main__':
    main()
