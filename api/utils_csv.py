import csv
import io
import re
from typing import List, Dict, Tuple


class CSVProcessor:
    """Procesador de archivos CSV para consultas masivas"""
    
    @staticmethod
    def detect_format(file_content: str) -> str:
        """
        Detecta el formato del CSV (coordenadas o direcciones)
        Returns: 'coordinates' o 'addresses'
        """
        reader = csv.DictReader(io.StringIO(file_content))
        headers = [h.lower().strip() for h in reader.fieldnames or []]
        
        # Detectar por headers
        if 'latitud' in headers and 'longitud' in headers:
            return 'coordinates'
        elif 'lat' in headers and ('lon' in headers or 'lng' in headers):
            return 'coordinates'
        elif 'direccion' in headers or 'address' in headers:
            return 'addresses'
        
        # Detectar por contenido de primera fila
        file_content_io = io.StringIO(file_content)
        reader = csv.reader(file_content_io)
        headers_raw = next(reader, None)
        first_row = next(reader, None)
        
        if first_row:
            # Si tiene 2 columnas con números, probablemente sean coordenadas
            if len(first_row) == 2:
                try:
                    float(first_row[0].replace(',', '.'))
                    float(first_row[1].replace(',', '.'))
                    return 'coordinates'
                except ValueError:
                    pass
        
        return 'addresses'
    
    @staticmethod
    def normalize_coordinate(coord_str: str) -> float:
        """
        Normaliza coordenadas (acepta coma o punto como decimal)
        Ejemplos: "6,2442" -> 6.2442, "6.2442" -> 6.2442
        """
        coord_clean = coord_str.strip().replace(',', '.')
        return float(coord_clean)
    
    @staticmethod
    def validate_coordinate(lat: float, lon: float) -> bool:
        """Valida que las coordenadas estén en rangos válidos"""
        # Colombia aproximadamente: lat 4° a 12°, lon -79° a -66°
        # Pero aceptamos rango más amplio para flexibilidad
        if not (-90 <= lat <= 90):
            return False
        if not (-180 <= lon <= 180):
            return False
        return True
    
    @staticmethod
    def parse_csv(file_obj) -> Tuple[str, List[Dict]]:
        """
        Parsea el archivo CSV y retorna formato y datos
        Returns: (formato, lista_de_registros)
        """
        # Leer contenido
        file_obj.seek(0)
        content = file_obj.read()
        
        # Detectar encoding
        try:
            content_str = content.decode('utf-8')
        except UnicodeDecodeError:
            content_str = content.decode('latin-1')
        
        # Detectar formato
        formato = CSVProcessor.detect_format(content_str)
        
        # Parsear según formato
        registros = []
        file_io = io.StringIO(content_str)
        reader = csv.DictReader(file_io)
        
        if formato == 'coordinates':
            for idx, row in enumerate(reader, 1):
                # Buscar columnas de latitud/longitud
                lat_key = next((k for k in row.keys() if 'lat' in k.lower()), None)
                lon_key = next((k for k in row.keys() if 'lon' in k.lower() or 'lng' in k.lower()), None)
                
                if not lat_key or not lon_key:
                    # Si no hay headers, asumir primer col=lat, segunda=lon
                    keys = list(row.keys())
                    if len(keys) >= 2:
                        lat_key, lon_key = keys[0], keys[1]
                
                try:
                    lat = CSVProcessor.normalize_coordinate(row[lat_key])
                    lon = CSVProcessor.normalize_coordinate(row[lon_key])
                    
                    if CSVProcessor.validate_coordinate(lat, lon):
                        registros.append({
                            'tipo': 'coordenada',
                            'latitud': lat,
                            'longitud': lon,
                            'entrada_original': f"{row[lat_key]},{row[lon_key]}",
                            'fila': idx
                        })
                    else:
                        registros.append({
                            'tipo': 'error',
                            'error': f'Coordenadas inválidas: {lat}, {lon}',
                            'entrada_original': f"{row[lat_key]},{row[lon_key]}",
                            'fila': idx
                        })
                except (ValueError, KeyError) as e:
                    registros.append({
                        'tipo': 'error',
                        'error': f'Error al parsear: {str(e)}',
                        'entrada_original': str(row),
                        'fila': idx
                    })
        
        else:  # addresses
            addr_key = next((k for k in reader.fieldnames if 'direcc' in k.lower() or 'address' in k.lower()), reader.fieldnames[0])
            
            file_io.seek(0)
            reader = csv.DictReader(file_io)
            
            for idx, row in enumerate(reader, 1):
                direccion = row.get(addr_key, '').strip()
                if direccion:
                    registros.append({
                        'tipo': 'direccion',
                        'direccion': direccion,
                        'entrada_original': direccion,
                        'fila': idx
                    })
        
        return formato, registros
    
    @staticmethod
    def generate_output_csv(resultados: List[Dict]) -> str:
        """
        Genera CSV de salida mapeando los datos del diccionario de la vista
        a un formato legible.
        """
        output = io.StringIO()
        
        if not resultados:
            return ''
        
        # Headers para el archivo final
        headers_map = {
            'entrada_original': 'Entrada Original',
            'coordenadas_consultadas': 'Coordenadas Consultadas',
            'tiene_cobertura': 'Tiene Cobertura',
            'isps_disponibles': 'ISPs Disponibles',
            'total_isps': 'Cantidad de ISPs',
            'distancia_minima_metros': 'Distancia Minima (metros)'
        }
        
        writer = csv.DictWriter(output, fieldnames=headers_map.values())
        writer.writeheader()
        
        for res in resultados:
            # Formatear la lista de ISPs
            isps = res.get('isps_disponibles', [])
            isps_str = ' | '.join(isps) if isps else 'Sin cobertura'
            
            # Formatear distancia
            dist = res.get('distancia_minima_metros', 'N/A')
            dist_str = f"{dist:.2f}" if isinstance(dist, (int, float)) else str(dist)
            
            writer.writerow({
                'Entrada Original': res.get('entrada_original', ''),
                'Coordenadas Consultadas': res.get('coordenadas_consultadas', ''),
                'Tiene Cobertura': 'Si' if res.get('tiene_cobertura') else 'No',
                'ISPs Disponibles': isps_str,
                'Cantidad de ISPs': res.get('total_isps', 0),
                'Distancia Minima (metros)': dist_str
            })
        
        return output.getvalue()
