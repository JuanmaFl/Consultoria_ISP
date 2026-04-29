from rest_framework import serializers
from django.contrib.gis.geos import GEOSGeometry
import json
from django.contrib.auth import get_user_model
from .models import CoberturaISP

Usuario = get_user_model()


class UsuarioSerializer(serializers.ModelSerializer):
    """Serializador para el modelo Usuario"""
    class Meta:
        model = Usuario
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'telefono', 'empresa']
        read_only_fields = ['id']


class CoberturaISPSerializer(serializers.ModelSerializer):
    """Serializador con geometría en formato GeoJSON"""
    
    class Meta:
        model = CoberturaISP
        fields = ['id', 'nombre', 'descripcion', 'proveedor', 'tipo_servicio', 'velocidad', 'archivo_origen', 'fecha_importacion', 'geom']
    
    def to_representation(self, instance):
        """Convertir a formato GeoJSON Feature"""
        # Convertir geometría a GeoJSON
        geometry = None
        if instance.geom:
            geometry = json.loads(instance.geom.geojson)
        
        return {
            'id': instance.id,
            'type': 'Feature',
            'geometry': geometry,
            'properties': {
                'nombre': instance.nombre,
                'descripcion': instance.descripcion,
                'proveedor': instance.proveedor,
                'tipo_servicio': instance.tipo_servicio,
                'velocidad': instance.velocidad,
                'archivo_origen': instance.archivo_origen,
                'fecha_importacion': instance.fecha_importacion.isoformat() if instance.fecha_importacion else None
            }
        }


class ConsultaCoberturaSerializer(serializers.Serializer):
    """Serializador para consultas de cobertura"""
    latitud = serializers.FloatField(required=True, min_value=-90, max_value=90)
    longitud = serializers.FloatField(required=True, min_value=-180, max_value=180)
    radio_metros = serializers.IntegerField(default=1000, min_value=1, max_value=5000)

class ResultadoCoberturaSerializer(serializers.Serializer):
    """Serializador para resultados de consulta de cobertura"""
    tiene_cobertura = serializers.BooleanField()
    isps_disponibles = serializers.ListField(child=serializers.CharField())
    total_isps = serializers.IntegerField()
    distancia_minima_metros = serializers.FloatField(allow_null=True)
    nodos_cercanos = serializers.ListField()
    rutas_cercanas = serializers.ListField()
    areas_cercanas = serializers.ListField()
    total_nodos = serializers.IntegerField()
    total_rutas = serializers.IntegerField()
    total_areas = serializers.IntegerField()
    total_elementos = serializers.IntegerField()
