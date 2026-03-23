"""
Utilidades para validación y procesamiento de archivos KMZ
"""
import zipfile
import xml.etree.ElementTree as ET
from django.contrib.gis.geos import GEOSGeometry, Point, LineString, Polygon, MultiPoint, MultiLineString, MultiPolygon
from django.core.exceptions import ValidationError
from django.db import transaction
import logging
import re

logger = logging.getLogger(__name__)

# Configuración
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_EXTENSIONS = ['.kmz', '.kml']

class KMZValidator:
    """Validador de archivos KMZ"""
    
    @staticmethod
    def validate_file_extension(filename):
        """Validar extensión del archivo"""
        ext = filename.lower()[filename.rfind('.'):]
        if ext not in ALLOWED_EXTENSIONS:
            raise ValidationError(f'Extensión no permitida. Solo se permiten: {", ".join(ALLOWED_EXTENSIONS)}')
        return True
    
    @staticmethod
    def validate_file_size(file_size):
        """Validar tamaño del archivo"""
        if file_size > MAX_FILE_SIZE:
            raise ValidationError(f'Archivo muy grande. Máximo permitido: {MAX_FILE_SIZE // (1024*1024)}MB')
        return True
    
    @staticmethod
    def validate_zip_structure(file_obj):
        """Validar que el KMZ es un ZIP válido"""
        try:
            with zipfile.ZipFile(file_obj, 'r') as zip_ref:
                # Verificar que tenga al menos un archivo .kml
                kml_files = [f for f in zip_ref.namelist() if f.lower().endswith('.kml')]
                if not kml_files:
                    raise ValidationError('El archivo KMZ no contiene ningún archivo KML')
                return kml_files[0]  # Retornar el primer KML encontrado
        except zipfile.BadZipFile:
            raise ValidationError('El archivo no es un ZIP válido')
        except Exception as e:
            raise ValidationError(f'Error al leer el archivo: {str(e)}')


class KMZProcessor:
    """Procesador de archivos KMZ"""
    
    # Namespace de KML
    NAMESPACES = {
        'kml': 'http://www.opengis.net/kml/2.2',
        'gx': 'http://www.google.com/kml/ext/2.2'
    }
    
    @staticmethod
    def extract_provider_from_filename(filename):
        """Extraer nombre del proveedor del nombre del archivo"""
        # Remover extensión
        name = filename.replace('.kmz', '').replace('.kml', '')
        
        # Patrones conocidos de ISPs
        providers = {
            'avidtel': 'Avidtel',
            'fibra_optica': 'Fibra Óptica Antioquia',
            'starnet': 'Starnet',
            'technet': 'Technet',
        }
        
        name_lower = name.lower()
        for key, provider in providers.items():
            if key in name_lower:
                return provider
        
        # Si no coincide con ninguno, usar el nombre del archivo limpio
        return name.replace('_', ' ').title()
    
    @staticmethod
    def parse_kml_content(kml_content):
        """Parsear contenido KML y extraer geometrías"""
        try:
            root = ET.fromstring(kml_content)
        except ET.ParseError as e:
            raise ValidationError(f'Error al parsear XML KML: {str(e)}')
        
        geometries = []
        
        # Buscar todos los Placemarks
        for placemark in root.findall('.//kml:Placemark', KMZProcessor.NAMESPACES):
            geometry_data = KMZProcessor._extract_placemark_data(placemark)
            if geometry_data:
                geometries.append(geometry_data)
        
        if not geometries:
            raise ValidationError('No se encontraron geometrías válidas en el archivo KML')
        
        return geometries
    
    @staticmethod
    def _extract_placemark_data(placemark):
        """Extraer datos de un Placemark"""
        data = {
            'nombre': None,
            'descripcion': None,
            'geometry': None
        }
        
        # Extraer nombre
        name_elem = placemark.find('kml:name', KMZProcessor.NAMESPACES)
        if name_elem is not None and name_elem.text:
            data['nombre'] = name_elem.text.strip()
        
        # Extraer descripción
        desc_elem = placemark.find('kml:description', KMZProcessor.NAMESPACES)
        if desc_elem is not None and desc_elem.text:
            data['descripcion'] = desc_elem.text.strip()
        
        # Extraer geometría
        geometry = KMZProcessor._extract_geometry(placemark)
        if geometry:
            data['geometry'] = geometry
            return data
        
        return None
    
    @staticmethod
    def _extract_geometry(placemark):
        """Extraer geometría de un Placemark"""
        ns = KMZProcessor.NAMESPACES
        
        # Intentar Point
        point = placemark.find('.//kml:Point/kml:coordinates', ns)
        if point is not None and point.text:
            return KMZProcessor._parse_point(point.text)
        
        # Intentar LineString
        linestring = placemark.find('.//kml:LineString/kml:coordinates', ns)
        if linestring is not None and linestring.text:
            return KMZProcessor._parse_linestring(linestring.text)
        
        # Intentar Polygon
        polygon = placemark.find('.//kml:Polygon', ns)
        if polygon is not None:
            return KMZProcessor._parse_polygon(polygon, ns)
        
        # Intentar MultiGeometry
        multigeom = placemark.find('.//kml:MultiGeometry', ns)
        if multigeom is not None:
            return KMZProcessor._parse_multigeometry(multigeom, ns)
        
        return None
    
    @staticmethod
    def _parse_point(coords_text):
        """Parsear coordenadas de un Point"""
        try:
            coords = coords_text.strip().split(',')
            lon, lat = float(coords[0]), float(coords[1])
            return Point(lon, lat, srid=4326)
        except Exception as e:
            logger.warning(f'Error parseando Point: {e}')
            return None
    
    @staticmethod
    def _parse_linestring(coords_text):
        """Parsear coordenadas de un LineString"""
        try:
            points = []
            for coord in coords_text.strip().split():
                parts = coord.split(',')
                if len(parts) >= 2:
                    lon, lat = float(parts[0]), float(parts[1])
                    points.append((lon, lat))
            
            if len(points) >= 2:
                return LineString(points, srid=4326)
        except Exception as e:
            logger.warning(f'Error parseando LineString: {e}')
        return None
    
    @staticmethod
    def _parse_polygon(polygon_elem, ns):
        """Parsear coordenadas de un Polygon"""
        try:
            # Obtener outer boundary
            outer_coords = polygon_elem.find('.//kml:outerBoundaryIs/kml:LinearRing/kml:coordinates', ns)
            if outer_coords is None or not outer_coords.text:
                return None
            
            outer_points = []
            for coord in outer_coords.text.strip().split():
                parts = coord.split(',')
                if len(parts) >= 2:
                    lon, lat = float(parts[0]), float(parts[1])
                    outer_points.append((lon, lat))
            
            if len(outer_points) >= 4:  # Polygon necesita al menos 4 puntos (cerrado)
                return Polygon(outer_points, srid=4326)
        except Exception as e:
            logger.warning(f'Error parseando Polygon: {e}')
        return None
    
    @staticmethod
    def _parse_multigeometry(multigeom_elem, ns):
        """Parsear MultiGeometry"""
        geometries = []
        
        # Buscar todos los tipos de geometrías
        for point in multigeom_elem.findall('.//kml:Point/kml:coordinates', ns):
            geom = KMZProcessor._parse_point(point.text)
            if geom:
                geometries.append(geom)
        
        for linestring in multigeom_elem.findall('.//kml:LineString/kml:coordinates', ns):
            geom = KMZProcessor._parse_linestring(linestring.text)
            if geom:
                geometries.append(geom)
        
        for polygon in multigeom_elem.findall('.//kml:Polygon', ns):
            geom = KMZProcessor._parse_polygon(polygon, ns)
            if geom:
                geometries.append(geom)
        
        # Crear MultiGeometry apropiada según los tipos encontrados
        if not geometries:
            return None
        
        # Determinar tipo predominante
        types = [g.geom_type for g in geometries]
        
        if all(t == 'Point' for t in types):
            return MultiPoint(geometries, srid=4326)
        elif all(t == 'LineString' for t in types):
            return MultiLineString(geometries, srid=4326)
        elif all(t == 'Polygon' for t in types):
            return MultiPolygon(geometries, srid=4326)
        else:
            # Si es mixto, retornar el primero
            return geometries[0] if geometries else None
    
    @staticmethod
    def check_duplicates(archivo_origen, proveedor=None):
        """Verificar si ya existe un archivo con el mismo nombre"""
        from .models import CoberturaISP
        
        query = CoberturaISP.objects.filter(archivo_origen=archivo_origen)
        if proveedor:
            query = query.filter(proveedor=proveedor)
        
        return query.exists()
    
    @staticmethod
    @transaction.atomic
    def save_geometries_to_db(geometries, archivo_origen, proveedor, usuario, archivo_fisico=None):
        """Guardar geometrías en la base de datos (transacción atómica)"""
        from .models import CoberturaISP
        
        saved_count = 0
        errors = []
        
        for idx, geom_data in enumerate(geometries):
            try:
                cobertura = CoberturaISP(
                    nombre=geom_data.get('nombre') or f'Elemento {idx + 1}',
                    descripcion=geom_data.get('descripcion'),
                    proveedor=proveedor,
                    archivo_origen=archivo_origen,
                    geom=geom_data['geometry'],
                    usuario_subida=usuario,
                    archivo_fisico=archivo_fisico
                )
                cobertura.save()
                saved_count += 1
                
            except Exception as e:
                error_msg = f'Error guardando elemento {idx + 1}: {str(e)}'
                errors.append(error_msg)
                logger.error(error_msg)
        
        if errors and saved_count == 0:
            # Si todos fallaron, hacer rollback
            raise ValidationError(f'No se pudo guardar ningún elemento. Errores: {"; ".join(errors)}')
        
        return {
            'saved_count': saved_count,
            'total_count': len(geometries),
            'errors': errors
        }

