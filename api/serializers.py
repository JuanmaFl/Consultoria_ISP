from rest_framework import serializers


class ConsultaCoberturaSerializer(serializers.Serializer):
    """Valida coordenadas para consultar cobertura."""

    latitud = serializers.FloatField(required=True, min_value=-90, max_value=90)
    longitud = serializers.FloatField(required=True, min_value=-180, max_value=180)
    radio_metros = serializers.IntegerField(default=1000, min_value=1, max_value=5000)


class ResultadoCoberturaSerializer(serializers.Serializer):
    """Respuesta de consulta de cobertura por coordenadas."""

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


class ResultadoBusquedaDireccionSerializer(serializers.Serializer):
    """Respuesta simplificada de busqueda por direccion."""

    direccion = serializers.CharField()
    hay_cobertura = serializers.BooleanField()
    isps_disponibles = serializers.ListField(child=serializers.CharField())
    total_isps = serializers.IntegerField()
    elementos = serializers.ListField()
