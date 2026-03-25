"""
Herramienta de Geolocalización - Conversión de coordenadas y ayudantes de mapeo
Excluye: Rastreo de ubicación en tiempo real, triangulación de señales
"""

import re
import math
import json
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from .utils import (
    Colors, print_banner, print_success, print_error, 
    print_warning, print_info, save_to_json
)


@dataclass
class Coordinates:
    """Clase para representar coordenadas geográficas"""
    latitude: float
    longitude: float
    altitude: Optional[float] = None
    
    def __post_init__(self):
        # Validar rangos
        if not -90 <= self.latitude <= 90:
            raise ValueError(f"Latitud debe estar entre -90 y 90, got {self.latitude}")
        if not -180 <= self.longitude <= 180:
            raise ValueError(f"Longitud debe estar entre -180 y 180, got {self.longitude}")
    
    def to_dms(self) -> Dict:
        """Convierte a grados, minutos, segundos"""
        return {
            'latitude': self._decimal_to_dms(self.latitude, 'N' if self.latitude >= 0 else 'S'),
            'longitude': self._decimal_to_dms(self.longitude, 'E' if self.longitude >= 0 else 'W')
        }
    
    def _decimal_to_dms(self, decimal: float, direction: str) -> Dict:
        """Convierte decimal a DMS"""
        decimal = abs(decimal)
        degrees = int(decimal)
        minutes_float = (decimal - degrees) * 60
        minutes = int(minutes_float)
        seconds = (minutes_float - minutes) * 60
        
        return {
            'degrees': degrees,
            'minutes': minutes,
            'seconds': round(seconds, 2),
            'direction': direction,
            'formatted': f"{degrees}° {minutes}' {seconds:.2f}\\\" {direction}"
        }
    
    def to_utm(self) -> Dict:
        """Convierte a UTM (Universal Transverse Mercator)"""
        # Implementación simplificada de conversión UTM
        lat = self.latitude
        lon = self.longitude
        
        # Determinar zona UTM
        zone_number = int((lon + 180) / 6) + 1
        
        # Determinar letra de zona
        zone_letters = "CDEFGHJKLMNPQRSTUVWXX"
        zone_letter = zone_letters[int((lat + 80) / 8)]
        
        return {
            'zone_number': zone_number,
            'zone_letter': zone_letter,
            'zone': f"{zone_number}{zone_letter}",
            'easting': None,  # Requeriría cálculo más complejo
            'northing': None,
            'note': 'Conversión UTM completa requiere librerías adicionales (pyproj)'
        }
    
    def to_mgrs(self) -> str:
        """Convierte a MGRS (Military Grid Reference System)"""
        utm = self.to_utm()
        return f"{utm['zone']} (MGRS completo requiere cálculo adicional)"
    
    def distance_to(self, other: 'Coordinates') -> float:
        """
        Calcula distancia a otras coordenadas usando fórmula de Haversine
        
        Returns:
            Distancia en kilómetros
        """
        R = 6371  # Radio de la Tierra en km
        
        lat1 = math.radians(self.latitude)
        lat2 = math.radians(other.latitude)
        delta_lat = math.radians(other.latitude - self.latitude)
        delta_lon = math.radians(other.longitude - self.longitude)
        
        a = (math.sin(delta_lat/2) * math.sin(delta_lat/2) +
             math.cos(lat1) * math.cos(lat2) *
             math.sin(delta_lon/2) * math.sin(delta_lon/2))
        
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    def bearing_to(self, other: 'Coordinates') -> float:
        """
        Calcula el rumbo (bearing) hacia otras coordenadas
        
        Returns:
            Rumbo en grados (0-360)
        """
        lat1 = math.radians(self.latitude)
        lat2 = math.radians(other.latitude)
        lon1 = math.radians(self.longitude)
        lon2 = math.radians(other.longitude)
        
        y = math.sin(lon2 - lon1) * math.cos(lat2)
        x = (math.cos(lat1) * math.sin(lat2) -
             math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1))
        
        bearing = math.degrees(math.atan2(y, x))
        return (bearing + 360) % 360
    
    def get_map_urls(self) -> Dict[str, str]:
        """Genera URLs a diferentes servicios de mapas"""
        lat, lon = self.latitude, self.longitude
        return {
            'google_maps': f"https://www.google.com/maps?q={lat},{lon}",
            'google_maps_satellite': f"https://www.google.com/maps?t=k&q={lat},{lon}",
            'openstreetmap': f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=15/{lat}/{lon}",
            'bing_maps': f"https://www.bing.com/maps?v=2&cp={lat}~{lon}&lvl=15",
            'wikimapia': f"http://wikimapia.org/#lat={lat}&lon={lon}&z=15",
            'google_earth_web': f"https://earth.google.com/web/@{lat},{lon},500a,0d,30y,0h,0t,0r",
            'osm_query': f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}"
        }
    
    def get_approximate_address(self) -> str:
        """Obtiene dirección aproximada usando Nominatim (requiere conexión)"""
        try:
            import requests
            url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={self.latitude}&lon={self.longitude}&zoom=18&addressdetails=1"
            headers = {'User-Agent': 'OSINT-Geolocation-Tool/1.0'}
            
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get('display_name', 'No disponible')
            return "No se pudo obtener dirección"
        except Exception as e:
            return f"Error: {str(e)}"


class GeolocationHelper:
    """Herramienta de ayuda para geolocalización"""
    
    def __init__(self):
        self.results = {}
    
    def parse_coordinates(self, input_str: str) -> Optional[Coordinates]:
        """
        Parsea coordenadas de diferentes formatos
        
        Args:
            input_str: String con coordenadas
        
        Returns:
            Objeto Coordinates o None
        """
        input_str = input_str.strip()
        
        # Intentar diferentes formatos
        
        # 1. Decimal simple: "40.7128, -74.0060" o "40.7128 -74.0060"
        decimal_pattern = r'(-?\\d+\\.?\\d*)[,\\s]+(-?\\d+\\.?\\d*)'
        match = re.search(decimal_pattern, input_str)
        if match:
            try:
                lat = float(match.group(1))
                lon = float(match.group(2))
                return Coordinates(lat, lon)
            except ValueError:
                pass
        
        # 2. Grados decimales con dirección: "40.7128° N, 74.0060° W"
        dd_pattern = r'(-?\\d+\\.?\\d*)°?\\s*([NS])[,\\s]+(-?\\d+\\.?\\d*)°?\\s*([EW])'
        match = re.search(dd_pattern, input_str, re.IGNORECASE)
        if match:
            try:
                lat = float(match.group(1))
                if match.group(2).upper() == 'S':
                    lat = -lat
                
                lon = float(match.group(3))
                if match.group(4).upper() == 'W':
                    lon = -lon
                
                return Coordinates(lat, lon)
            except ValueError:
                pass
        
        # 3. DMS: "40° 42' 46" N" o "40°42'46\"N"
        dms_pattern = r'(\d+)°\s*(\d+)\'\s*(\d+\.?\d*)\"?\s*([NS])[,\\s]+(\d+)°\s*(\d+)\'\s*(\d+\.?\d*)\"?\s*([EW])'
        match = re.search(dms_pattern, input_str, re.IGNORECASE)
        if match:
            try:
                lat_deg = int(match.group(1))
                lat_min = int(match.group(2))
                lat_sec = float(match.group(3))
                lat_dir = match.group(4).upper()
                
                lon_deg = int(match.group(5))
                lon_min = int(match.group(6))
                lon_sec = float(match.group(7))
                lon_dir = match.group(8).upper()
                
                lat = lat_deg + lat_min/60 + lat_sec/3600
                if lat_dir == 'S':
                    lat = -lat
                
                lon = lon_deg + lon_min/60 + lon_sec/3600
                if lon_dir == 'W':
                    lon = -lon
                
                return Coordinates(lat, lon)
            except (ValueError, IndexError):
                pass
        
        return None
    
    def analyze_coordinates(self, lat: float, lon: float, altitude: float = None) -> Dict:
        """
        Realiza análisis completo de coordenadas
        
        Args:
            lat: Latitud
            lon: Longitud
            altitude: Altitud opcional
        
        Returns:
            Dict con análisis completo
        """
        print_banner(f"ANÁLISIS DE COORDENADAS: {lat}, {lon}")
        
        try:
            coords = Coordinates(lat, lon, altitude)
        except ValueError as e:
            print_error(f"Coordenadas inválidas: {str(e)}")
            return {'error': str(e)}
        
        result = {
            'input': {
                'latitude': lat,
                'longitude': lon,
                'altitude': altitude
            },
            'formats': {},
            'location_info': {},
            'map_urls': {},
            'analysis': {}
        }
        
        # Diferentes formatos
        print(f"{Colors.BOLD}FORMATOS DE COORDENADAS:{Colors.ENDC}")
        
        # Decimal
        print(f"  Decimal: {lat:.6f}, {lon:.6f}")
        result['formats']['decimal'] = f"{lat:.6f}, {lon:.6f}"
        
        # DMS
        dms = coords.to_dms()
        print(f"  DMS Lat: {dms['latitude']['formatted']}")
        print(f"  DMS Lon: {dms['longitude']['formatted']}")
        result['formats']['dms'] = dms
        
        # UTM
        utm = coords.to_utm()
        print(f"  UTM Zona: {utm['zone']}")
        result['formats']['utm'] = utm
        
        # MGRS
        mgrs = coords.to_mgrs()
        print(f"  MGRS: {mgrs}")
        result['formats']['mgrs'] = mgrs
        
        # URLs de mapas
        print(f"\n{Colors.BOLD}ENLACES A MAPAS:{Colors.ENDC}")
        map_urls = coords.get_map_urls()
        for name, url in map_urls.items():
            print(f"  {name}: {url}")
        result['map_urls'] = map_urls
        
        # Información de ubicación
        print(f"\n{Colors.BOLD}INFORMACIÓN DE UBICACIÓN:{Colors.ENDC}")
        
        # Determinar hemisferios
        result['location_info']['hemisphere_ns'] = 'Norte' if lat >= 0 else 'Sur'
        result['location_info']['hemisphere_ew'] = 'Este' if lon >= 0 else 'Oeste'
        result['location_info']['meridian'] = 'Este del meridiano de Greenwich' if lon >= 0 else 'Oeste del meridiano de Greenwich'
        
        print(f"  Hemisferio: {result['location_info']['hemisphere_ns']}, {result['location_info']['hemisphere_ew']}")
        
        # Zona horaria aproximada
        timezone_offset = round(lon / 15)
        result['location_info']['approx_timezone'] = f"UTC{timezone_offset:+d}"
        print(f"  Zona horaria aproximada: {result['location_info']['approx_timezone']}")
        
        # Intentar obtener dirección
        print(f"\n{Colors.BOLD}DIRECCIÓN APROXIMADA:{Colors.ENDC}")
        address = coords.get_approximate_address()
        print(f"  {address}")
        result['location_info']['approx_address'] = address
        
        # Análisis adicional
        print(f"\n{Colors.BOLD}ANÁLISIS:{Colors.ENDC}")
        
        # Verificar si es agua o tierra (aproximado)
        # Océanos están generalmente en latitudes extremas o longitudes específicas
        is_likely_ocean = False
        if abs(lat) > 70:  # Cercano a polos
            is_likely_ocean = True
        result['analysis']['likely_ocean'] = is_likely_ocean
        
        # Clima aproximado basado en latitud
        if abs(lat) < 23.5:
            climate = "Tropical"
        elif abs(lat) < 35:
            climate = "Subtropical"
        elif abs(lat) < 66.5:
            climate = "Templado"
        else:
            climate = "Polar"
        
        result['analysis']['climate_zone'] = climate
        print(f"  Zona climática: {climate}")
        
        if altitude:
            print(f"  Altitud: {altitude} metros")
            if altitude > 0:
                print(f"  Elevación: {altitude}m sobre el nivel del mar")
        
        self.results = result
        return result
    
    def calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> Dict:
        """
        Calcula distancia y rumbo entre dos puntos
        
        Args:
            lat1, lon1: Primer punto
            lat2, lon2: Segundo punto
        
        Returns:
            Dict con distancia y rumbo
        """
        print_banner(f"CÁLCULO DE DISTANCIA")
        
        try:
            point1 = Coordinates(lat1, lon1)
            point2 = Coordinates(lat2, lon2)
        except ValueError as e:
            print_error(f"Coordenadas inválidas: {str(e)}")
            return {'error': str(e)}
        
        distance_km = point1.distance_to(point2)
        distance_miles = distance_km * 0.621371
        bearing = point1.bearing_to(point2)
        
        # Determinar dirección cardinal
        directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
        index = round(bearing / 45) % 8
        cardinal = directions[index]
        
        result = {
            'point1': {'lat': lat1, 'lon': lon1},
            'point2': {'lat': lat2, 'lon': lon2},
            'distance_km': round(distance_km, 2),
            'distance_miles': round(distance_miles, 2),
            'bearing_degrees': round(bearing, 2),
            'bearing_cardinal': cardinal,
            'direction': f"{cardinal} ({bearing:.1f}°)"
        }
        
        print(f"{Colors.BOLD}PUNTO 1:{Colors.ENDC} {lat1:.6f}, {lon1:.6f}")
        print(f"{Colors.BOLD}PUNTO 2:{Colors.ENDC} {lat2:.6f}, {lon2:.6f}")
        print(f"\n{Colors.BOLD}RESULTADOS:{Colors.ENDC}")
        print(f"  Distancia: {distance_km:.2f} km ({distance_miles:.2f} millas)")
        print(f"  Rumbo: {bearing:.1f}° ({cardinal})")
        
        return result
    
    def batch_convert(self, coordinates_list: List[Tuple[float, float]]) -> List[Dict]:
        """
        Convierte múltiples coordenadas a diferentes formatos
        
        Args:
            coordinates_list: Lista de tuplas (lat, lon)
        
        Returns:
            Lista de resultados
        """
        print_banner(f"CONVERSIÓN BATCH: {len(coordinates_list)} COORDENADAS")
        
        results = []
        for i, (lat, lon) in enumerate(coordinates_list, 1):
            print(f"\n{Colors.BOLD}[{i}/{len(coordinates_list)}]{Colors.ENDC} {lat}, {lon}")
            result = self.analyze_coordinates(lat, lon)
            results.append(result)
        
        return results
    
    def save_results(self, filename: str = None):
        """Guarda los resultados en JSON"""
        if not filename:
            coords = self.results.get('input', {})
            lat = coords.get('latitude', 'unknown')
            lon = coords.get('longitude', 'unknown')
            filename = f"geolocation_{lat}_{lon}"
        return save_to_json(self.results, filename)


def main():
    """Función principal para uso en línea de comandos"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Herramienta de Geolocalización OSINT',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python geolocation_helper.py --coords "40.7128, -74.0060"
  python geolocation_helper.py --lat 40.7128 --lon -74.0060
  python geolocation_helper.py --distance 40.7128 -74.0060 51.5074 -0.1278
  python geolocation_helper.py --parse "40° 42' 46" N, 74° 0' 21" W"
        """
    )
    
    parser.add_argument('--coords', help='Coordenadas en formato "lat, lon"')
    parser.add_argument('--lat', type=float, help='Latitud')
    parser.add_argument('--lon', type=float, help='Longitud')
    parser.add_argument('--alt', type=float, help='Altitud en metros')
    parser.add_argument('--parse', help='Parsear coordenadas en formato DMS o variado')
    parser.add_argument('--distance', nargs=4, type=float, metavar=('LAT1', 'LON1', 'LAT2', 'LON2'),
                       help='Calcular distancia entre dos puntos')
    parser.add_argument('--save', action='store_true', help='Guardar resultados en JSON')
    
    args = parser.parse_args()
    
    helper = GeolocationHelper()
    
    if args.distance:
        lat1, lon1, lat2, lon2 = args.distance
        results = helper.calculate_distance(lat1, lon1, lat2, lon2)
        if args.save:
            save_to_json(results, f"distance_calculation")
    
    elif args.parse:
        coords = helper.parse_coordinates(args.parse)
        if coords:
            print_success(f"Coordenadas parseadas: {coords.latitude}, {coords.longitude}")
            results = helper.analyze_coordinates(coords.latitude, coords.longitude)
            if args.save:
                helper.save_results()
        else:
            print_error("No se pudieron parsear las coordenadas")
    
    elif args.coords:
        coords = helper.parse_coordinates(args.coords)
        if coords:
            results = helper.analyze_coordinates(coords.latitude, coords.longitude, args.alt)
            if args.save:
                helper.save_results()
    
    elif args.lat is not None and args.lon is not None:
        results = helper.analyze_coordinates(args.lat, args.lon, args.alt)
        if args.save:
            helper.save_results()
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
