from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import CoberturaISP

Usuario = get_user_model()

class UsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ['id', 'username', 'email']

class RegistroUsuarioSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)

# --- ESTO ES LO QUE TE FALTABA ---

class CoberturaISPSerializer(serializers.ModelSerializer):
    class Meta:
        model = CoberturaISP
        fields = '__all__'

class ConsultaCoberturaSerializer(serializers.Serializer):
    latitud = serializers.FloatField()
    longitud = serializers.FloatField()
    radio_metros = serializers.IntegerField(default=1000)

class ResultadoCoberturaSerializer(serializers.Serializer):
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
    direccion = serializers.CharField()
    hay_cobertura = serializers.BooleanField()
    isps_disponibles = serializers.ListField()
    total_isps = serializers.IntegerField()
    elementos = serializers.ListField()

# Este también es necesario para una de tus funciones en views.py
class ResultadoBusquedaDireccionSerializer(serializers.Serializer):
    direccion_completa = serializers.CharField()
    latitud = serializers.FloatField()
    longitud = serializers.FloatField()