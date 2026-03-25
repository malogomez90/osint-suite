"""
Extractor de Metadatos de Imágenes - Extracción y análisis de datos EXIF
Excluye: Esteganografía avanzada, cracking de contraseñas de imágenes
"""

import os
import json
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import piexif
from .utils import (
    Colors, print_banner, print_success, print_error, 
    print_warning, print_info, save_to_json, format_timestamp
)


class ImageMetadataExtractor:
    """Extractor y analizador de metadatos de imágenes"""
    
    def __init__(self):
        self.results = {}
        self.supported_formats = ['.jpg', '.jpeg', '.tiff', '.tif', '.png', '.gif', '.bmp', '.webp']
    
    def extract_exif(self, image_path: str) -> Dict:
        """
        Extrae metadatos EXIF de una imagen
        
        Args:
            image_path: Ruta a la imagen
        
        Returns:
            Dict con metadatos EXIF
        """
        print_info(f"Extrayendo EXIF de: {os.path.basename(image_path)}")
        
        result = {
            'file_path': image_path,
            'file_name': os.path.basename(image_path),
            'has_exif': False,
            'exif_data': {},
            'gps_info': None,
            'camera_info': {},
            'timestamps': {},
            'error': None
        }
        
        try:
            if not os.path.exists(image_path):
                result['error'] = 'Archivo no encontrado'
                print_error(result['error'])
                return result
            
            # Verificar formato
            ext = os.path.splitext(image_path)[1].lower()
            if ext not in self.supported_formats:
                result['error'] = f'Formato no soportado: {ext}'
                print_warning(result['error'])
            
            # Abrir imagen
            with Image.open(image_path) as img:
                result['format'] = img.format
                result['mode'] = img.mode
                result['size'] = img.size
                result['width'] = img.width
                result['height'] = img.height
                
                # Extraer EXIF
                exif_data = img._getexif()
                
                if exif_data:
                    result['has_exif'] = True
                    
                    # Procesar todos los tags EXIF
                    for tag_id, value in exif_data.items():
                        tag_name = TAGS.get(tag_id, tag_id)
                        
                        # Decodificar valor si es bytes
                        if isinstance(value, bytes):
                            try:
                                value = value.decode('utf-8', errors='ignore')
                            except:
                                value = str(value)
                        
                        result['exif_data'][tag_name] = value
                        
                        # Categorizar información
                        self._categorize_metadata(result, tag_name, value)
                    
                    # Extraer GPS
                    gps_info = self._extract_gps(exif_data)
                    if gps_info:
                        result['gps_info'] = gps_info
                        print_success(f"Información GPS encontrada!")
                    
                    print_success(f"Metadatos EXIF extraídos ({len(result['exif_data'])} campos)")
                else:
                    print_warning("No se encontraron metadatos EXIF")
                
                # Extraer información de la imagen misma
                result['image_info'] = {
                    'format': img.format,
                    'format_description': img.format_description if hasattr(img, 'format_description') else None,
                    'mode': img.mode,
                    'size': img.size,
                    'width': img.width,
                    'height': img.height,
                    'info': dict(img.info) if img.info else {}
                }
                
        except Exception as e:
            result['error'] = f'Error al procesar imagen: {str(e)}'
            print_error(result['error'])
        
        return result
    
    def _categorize_metadata(self, result: Dict, tag_name: str, value: Any):
        """Categoriza los metadatos en grupos"""
        
        # Información de cámara
        camera_tags = ['Make', 'Model', 'LensModel', 'LensSpecification', 
                      'BodySerialNumber', 'LensSerialNumber', 'CameraOwnerName']
        if tag_name in camera_tags:
            result['camera_info'][tag_name] = str(value)
        
        # Timestamps
        timestamp_tags = ['DateTime', 'DateTimeOriginal', 'DateTimeDigitized', 
                         'GPSDateStamp', 'GPSTimeStamp', 'ModifyDate', 'CreateDate']
        if tag_name in timestamp_tags:
            result['timestamps'][tag_name] = str(value)
        
        # Configuración de captura
        capture_tags = ['ExposureTime', 'FNumber', 'ISOSpeedRatings', 'FocalLength',
                       'Flash', 'WhiteBalance', 'MeteringMode', 'ExposureProgram',
                       'ExposureBiasValue', 'MaxApertureValue', 'SubjectDistance']
        if tag_name in capture_tags:
            if 'capture_settings' not in result:
                result['capture_settings'] = {}
            result['capture_settings'][tag_name] = str(value)
        
        # Información de software
        software_tags = ['Software', 'ImageDescription', 'Artist', 'Copyright',
                        'HostComputer', 'ProcessingSoftware']
        if tag_name in software_tags:
            if 'software_info' not in result:
                result['software_info'] = {}
            result['software_info'][tag_name] = str(value)
    
    def _extract_gps(self, exif_data: Dict) -> Optional[Dict]:
        """Extrae información GPS de los metadatos EXIF"""
        gps_info = {}
        
        # Buscar tag GPSInfo
        gps_tag_id = None
        for tag_id, tag_name in TAGS.items():
            if tag_name == 'GPSInfo':
                gps_tag_id = tag_id
                break
        
        if not gps_tag_id or gps_tag_id not in exif_data:
            return None
        
        gps_data = exif_data[gps_tag_id]
        
        # Mapear tags GPS
        gps_tags = {
            1: 'GPSLatitudeRef',      # N o S
            2: 'GPSLatitude',         # (grados, minutos, segundos)
            3: 'GPSLongitudeRef',     # E o W
            4: 'GPSLongitude',        # (grados, minutos, segundos)
            5: 'GPSAltitudeRef',      # 0 = sobre nivel del mar, 1 = bajo nivel del mar
            6: 'GPSAltitude',         # en metros
            7: 'GPSTimeStamp',        # (hora, minuto, segundo)
            8: 'GPSSatellites',       # string
            9: 'GPSStatus',           # A = medición activa, V = medición void
            10: 'GPSMeasureMode',     # 2 = 2D, 3 = 3D
            11: 'GPSDOP',             # Dilution of precision
            12: 'GPSSpeedRef',        # K = km/h, M = mph, N = knots
            13: 'GPSSpeed',           # velocidad
            14: 'GPSTrackRef',        # dirección del movimiento
            15: 'GPSTrack',           # ángulo de dirección
            16: 'GPSImgDirectionRef', # dirección de la imagen
            17: 'GPSImgDirection',    # ángulo de dirección de imagen
            18: 'GPSMapDatum',        # datum geodésico
            19: 'GPSDestLatitudeRef', # N o S
            20: 'GPSDestLatitude',    # latitud destino
            21: 'GPSDestLongitudeRef',# E o W
            22: 'GPSDestLongitude',   # longitud destino
            23: 'GPSDestBearingRef',  # dirección al destino
            24: 'GPSDestBearing',     # ángulo al destino
            25: 'GPSDestDistanceRef', # unidad de distancia al destino
            26: 'GPSDestDistance',    # distancia al destino
            27: 'GPSProcessingMethod',# método de procesamiento
            28: 'GPSAreaInformation', # nombre del área
            29: 'GPSDateStamp',       # fecha GPS
            30: 'GPSDifferential'     # corrección diferencial
        }
        
        for key in gps_data.keys():
            tag_name = gps_tags.get(key, f'Unknown_GPS_{key}')
            gps_info[tag_name] = gps_data[key]
        
        # Convertir coordenadas a formato decimal
        if 'GPSLatitude' in gps_info and 'GPSLatitudeRef' in gps_info:
            lat = self._convert_dms_to_decimal(
                gps_info['GPSLatitude'], 
                gps_info['GPSLatitudeRef']
            )
            gps_info['latitude_decimal'] = lat
        
        if 'GPSLongitude' in gps_info and 'GPSLongitudeRef' in gps_info:
            lon = self._convert_dms_to_decimal(
                gps_info['GPSLongitude'],
                gps_info['GPSLongitudeRef']
            )
            gps_info['longitude_decimal'] = lon
        
        # Generar enlaces a mapas
        if 'latitude_decimal' in gps_info and 'longitude_decimal' in gps_info:
            lat = gps_info['latitude_decimal']
            lon = gps_info['longitude_decimal']
            gps_info['google_maps_url'] = f'https://www.google.com/maps?q={lat},{lon}'
            gps_info['openstreetmap_url'] = f'https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=15/{lat}/{lon}'
        
        return gps_info if gps_info else None
    
    def _convert_dms_to_decimal(self, dms, ref):
        """Convierte grados/minutos/segundos a decimal"""
        try:
            degrees = dms[0]
            minutes = dms[1]
            seconds = dms[2]
            
            decimal = float(degrees) + float(minutes) / 60 + float(seconds) / 3600
            
            if ref in ['S', 'W']:
                decimal = -decimal
            
            return round(decimal, 6)
        except:
            return None
    
    def analyze_image(self, image_path: str) -> Dict:
        """
        Realiza un análisis completo de una imagen
        
        Args:
            image_path: Ruta a la imagen
        
        Returns:
            Dict con análisis completo
        """
        print_banner(f"ANÁLISIS DE IMAGEN: {os.path.basename(image_path)}")
        
        # Extraer metadatos
        result = self.extract_exif(image_path)
        
        if result['error']:
            return result
        
        # Análisis adicional
        print(f"\n{Colors.BOLD}INFORMACIÓN DEL ARCHIVO:{Colors.ENDC}")
        print(f"  Nombre: {result['file_name']}")
        print(f"  Formato: {result.get('format', 'Desconocido')}")
        print(f"  Dimensiones: {result.get('width', '?')} x {result.get('height', '?')} px")
        print(f"  Modo: {result.get('mode', 'Desconocido')}")
        
        # Información de cámara
        if result.get('camera_info'):
            print(f"\n{Colors.BOLD}INFORMACIÓN DE CÁMARA:{Colors.ENDC}")
            for key, value in result['camera_info'].items():
                print(f"  {key}: {value}")
        
        # Timestamps
        if result.get('timestamps'):
            print(f"\n{Colors.BOLD}FECHAS Y HORAS:{Colors.ENDC}")
            for key, value in result['timestamps'].items():
                print(f"  {key}: {value}")
        
        # Configuración de captura
        if result.get('capture_settings'):
            print(f"\n{Colors.BOLD}CONFIGURACIÓN DE CAPTURA:{Colors.ENDC}")
            for key, value in result['capture_settings'].items():
                print(f"  {key}: {value}")
        
        # GPS
        if result.get('gps_info'):
            gps = result['gps_info']
            print(f"\n{Colors.OKGREEN}{Colors.BOLD}INFORMACIÓN GPS:{Colors.ENDC}")
            if 'latitude_decimal' in gps:
                print(f"  Latitud: {gps['latitude_decimal']}")
            if 'longitude_decimal' in gps:
                print(f"  Longitud: {gps['longitude_decimal']}")
            if 'GPSAltitude' in gps:
                print(f"  Altitud: {gps['GPSAltitude']} m")
            if 'google_maps_url' in gps:
                print(f"\n  {Colors.OKCYAN}Google Maps:{Colors.ENDC} {gps['google_maps_url']}")
            if 'openstreetmap_url' in gps:
                print(f"  {Colors.OKCYAN}OpenStreetMap:{Colors.ENDC} {gps['openstreetmap_url']}")
        
        # Software
        if result.get('software_info'):
            print(f"\n{Colors.BOLD}INFORMACIÓN DE SOFTWARE:{Colors.ENDC}")
            for key, value in result['software_info'].items():
                print(f"  {key}: {value}")
        
        # Recomendaciones de privacidad
        print(f"\n{Colors.BOLD}ANÁLISIS DE PRIVACIDAD:{Colors.ENDC}")
        privacy_risks = []
        
        if result.get('gps_info'):
            privacy_risks.append("Ubicación GPS exacta expuesta")
        if result.get('timestamps'):
            privacy_risks.append("Fechas/horas de captura visibles")
        if result.get('camera_info', {}).get('BodySerialNumber'):
            privacy_risks.append("Número de serie de cámara expuesto")
        if result.get('camera_info', {}).get('CameraOwnerName'):
            privacy_risks.append("Nombre del propietario de cámara en metadatos")
        if result.get('software_info', {}).get('HostComputer'):
            privacy_risks.append("Nombre del equipo host visible")
        
        if privacy_risks:
            print_warning("Riesgos de privacidad detectados:")
            for risk in privacy_risks:
                print_warning(f"  • {risk}")
        else:
            print_success("No se detectaron riesgos de privacidad obvios")
        
        result['privacy_analysis'] = {
            'risks_found': privacy_risks,
            'risk_count': len(privacy_risks),
            'recommendation': 'Eliminar metadatos antes de compartir públicamente' if privacy_risks else 'Sin acciones necesarias'
        }
        
        self.results = result
        return result
    
    def batch_process(self, directory: str, recursive: bool = False) -> List[Dict]:
        """
        Procesa múltiples imágenes en un directorio
        
        Args:
            directory: Directorio a procesar
            recursive: Si se debe procesar recursivamente
        
        Returns:
            Lista de resultados
        """
        print_banner(f"PROCESAMIENTO BATCH: {directory}")
        
        results = []
        image_files = []
        
        # Recopilar archivos
        if recursive:
            for root, dirs, files in os.walk(directory):
                for file in files:
                    if any(file.lower().endswith(ext) for ext in self.supported_formats):
                        image_files.append(os.path.join(root, file))
        else:
            for file in os.listdir(directory):
                if any(file.lower().endswith(ext) for ext in self.supported_formats):
                    image_files.append(os.path.join(directory, file))
        
        print_info(f"Encontradas {len(image_files)} imágenes")
        
        # Procesar cada imagen
        for i, image_path in enumerate(image_files, 1):
            print(f"\n{Colors.BOLD}[{i}/{len(image_files)}]{Colors.ENDC} {os.path.basename(image_path)}")
            result = self.extract_exif(image_path)
            results.append(result)
        
        # Resumen
        with_gps = sum(1 for r in results if r.get('gps_info'))
        with_exif = sum(1 for r in results if r.get('has_exif'))
        
        print(f"\n{Colors.BOLD}RESUMEN BATCH:{Colors.ENDC}")
        print(f"  Total procesadas: {len(results)}")
        print(f"  Con metadatos EXIF: {with_exif}")
        print(f"  Con información GPS: {with_gps}")
        
        return results
    
    def remove_metadata(self, image_path: str, output_path: str = None) -> bool:
        """
        Elimina todos los metadatos de una imagen
        
        Args:
            image_path: Ruta de la imagen original
            output_path: Ruta de salida (si es None, sobrescribe)
        
        Returns:
            True si tuvo éxito
        """
        print_info(f"Eliminando metadatos de: {os.path.basename(image_path)}")
        
        try:
            with Image.open(image_path) as img:
                # Crear nueva imagen sin metadatos
                data = list(img.getdata())
                new_img = Image.new(img.mode, img.size)
                new_img.putdata(data)
                
                # Guardar sin EXIF
                if output_path is None:
                    base, ext = os.path.splitext(image_path)
                    output_path = f"{base}_cleaned{ext}"
                
                new_img.save(output_path)
                print_success(f"Imagen limpia guardada en: {output_path}")
                return True
                
        except Exception as e:
            print_error(f"Error al eliminar metadatos: {str(e)}")
            return False
    
    def save_results(self, filename: str = None):
        """Guarda los resultados en JSON"""
        if not filename:
            filename = f"image_analysis_{self.results.get('file_name', 'unknown')}"
        return save_to_json(self.results, filename)


def main():
    """Función principal para uso en línea de comandos"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Extractor de Metadatos de Imágenes OSINT',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python image_metadata.py -i foto.jpg
  python image_metadata.py -i foto.jpg --save
  python image_metadata.py --batch ./fotos/ --recursive
  python image_metadata.py -i foto.jpg --clean -o foto_limpia.jpg
        """
    )
    
    parser.add_argument('-i', '--image', help='Ruta a la imagen a analizar')
    parser.add_argument('--batch', help='Directorio con imágenes a procesar')
    parser.add_argument('-r', '--recursive', action='store_true', help='Procesar recursivamente')
    parser.add_argument('--save', action='store_true', help='Guardar resultados en JSON')
    parser.add_argument('--clean', action='store_true', help='Eliminar metadatos')
    parser.add_argument('-o', '--output', help='Ruta de salida para imagen limpia')
    
    args = parser.parse_args()
    
    extractor = ImageMetadataExtractor()
    
    if args.image:
        results = extractor.analyze_image(args.image)
        
        if args.clean:
            extractor.remove_metadata(args.image, args.output)
        
        if args.save:
            extractor.save_results()
    
    elif args.batch:
        results = extractor.batch_process(args.batch, args.recursive)
        
        if args.save:
            save_to_json(results, f"batch_image_analysis")
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
