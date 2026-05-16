"""
Vistas del módulo de análisis de factibilidad
"""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import render
from django.conf import settings
from .models import MunicipioData, AnalisisFactibilidad
from .services_factibilidad import analizar_factibilidad


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def listar_municipios(request):
    """
    Listar municipios disponibles para análisis
    GET /api/factibilidad/municipios/?departamento=Antioquia
    """
    departamento = request.query_params.get('departamento', '')
    query = MunicipioData.objects.all()

    if departamento:
        query = query.filter(departamento__icontains=departamento)

    municipios = query.values(
        'codigo_dane', 'nombre', 'departamento',
        'poblacion_total', 'hogares', 'latitud', 'longitud',
        'mintic_tiene_fibra', 'mintic_penetracion_pct'
    ).order_by('departamento', 'nombre')

    departamentos = list(
        MunicipioData.objects.values_list('departamento', flat=True)
        .distinct().order_by('departamento')
    )

    return Response({
        'total': municipios.count(),
        'departamentos': departamentos,
        'municipios': list(municipios),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_analisis(request):
    """
    Generar análisis de factibilidad para una zona
    POST /api/factibilidad/analizar/
    Body:
    {
        "tipo_zona": "municipio" | "departamento" | "radio",
        "municipio": "Medellín",           # si tipo_zona = municipio
        "departamento": "Antioquia",        # siempre requerido para municipio
        "latitud": 6.2442,                 # si tipo_zona = radio
        "longitud": -75.5812,              # si tipo_zona = radio
        "radio_km": 10                     # si tipo_zona = radio
    }
    """
    tipo_zona = request.data.get('tipo_zona')

    if tipo_zona not in ['municipio', 'departamento', 'radio']:
        return Response(
            {'error': 'tipo_zona debe ser: municipio, departamento o radio'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Construir parámetros y nombre de zona
    if tipo_zona == 'municipio':
        municipio = request.data.get('municipio')
        departamento = request.data.get('departamento', '')
        if not municipio:
            return Response(
                {'error': 'Se requiere "municipio"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        parametros = {'municipio': municipio, 'departamento': departamento}
        zona_nombre = f"{municipio}, {departamento}" if departamento else municipio

    elif tipo_zona == 'departamento':
        departamento = request.data.get('departamento')
        if not departamento:
            return Response(
                {'error': 'Se requiere "departamento"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        parametros = {'departamento': departamento}
        zona_nombre = departamento

    elif tipo_zona == 'radio':
        lat = request.data.get('latitud')
        lng = request.data.get('longitud')
        radio_km = request.data.get('radio_km', 10)
        if not lat or not lng:
            return Response(
                {'error': 'Se requieren "latitud" y "longitud"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        parametros = {
            'latitud': float(lat),
            'longitud': float(lng),
            'radio_km': int(radio_km)
        }
        zona_nombre = f"Zona ({lat}, {lng}) radio {radio_km}km"

    # Llamar servicio principal
    resultado = analizar_factibilidad(
        tipo_zona=tipo_zona,
        zona_nombre=zona_nombre,
        parametros=parametros,
        usuario=request.user,
    )

    if 'error' in resultado:
        return Response(resultado, status=status.HTTP_400_BAD_REQUEST)

    analisis = resultado['analisis']

    return Response({
        'desde_cache': resultado['desde_cache'],
        'analisis': {
            'id': analisis.id,
            'zona_nombre': analisis.zona_nombre,
            'tipo_zona': analisis.tipo_zona,
            'score_factibilidad': analisis.score_factibilidad,
            'recomendacion': analisis.recomendacion,
            'analisis_texto': analisis.analisis_texto,
            'isps_presentes': analisis.isps_presentes,
            'km_fibra_estimados': analisis.km_fibra_estimados,
            'cobertura_isp_count': analisis.cobertura_isp_count,
            'poblacion_zona': analisis.poblacion_zona,
            'hogares_zona': analisis.hogares_zona,
            'penetracion_actual_pct': analisis.penetracion_actual_pct,
            'fecha_generacion': analisis.fecha_generacion,
            'fecha_expiracion': analisis.fecha_expiracion,
        }
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def historial_analisis(request):
    """
    Historial de análisis generados
    GET /api/factibilidad/historial/
    """
    analisis = AnalisisFactibilidad.objects.select_related('usuario').order_by('-fecha_generacion')[:20]

    return Response({
        'total': analisis.count(),
        'analisis': [
            {
                'id': a.id,
                'zona_nombre': a.zona_nombre,
                'tipo_zona': a.tipo_zona,
                'score_factibilidad': a.score_factibilidad,
                'recomendacion': a.recomendacion,
                'fecha_generacion': a.fecha_generacion,
                'esta_vigente': a.esta_vigente,
                'usuario': a.usuario.username if a.usuario else None,
            }
            for a in analisis
        ]
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def detalle_analisis(request, analisis_id):
    """
    Detalle de un análisis específico
    GET /api/factibilidad/analisis/<id>/
    """
    try:
        analisis = AnalisisFactibilidad.objects.get(id=analisis_id)
    except AnalisisFactibilidad.DoesNotExist:
        return Response({'error': 'Análisis no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    return Response({
        'id': analisis.id,
        'zona_nombre': analisis.zona_nombre,
        'tipo_zona': analisis.tipo_zona,
        'zona_parametros': analisis.zona_parametros,
        'score_factibilidad': analisis.score_factibilidad,
        'recomendacion': analisis.recomendacion,
        'analisis_texto': analisis.analisis_texto,
        'isps_presentes': analisis.isps_presentes,
        'km_fibra_estimados': analisis.km_fibra_estimados,
        'cobertura_isp_count': analisis.cobertura_isp_count,
        'poblacion_zona': analisis.poblacion_zona,
        'hogares_zona': analisis.hogares_zona,
        'penetracion_actual_pct': analisis.penetracion_actual_pct,
        'fecha_generacion': analisis.fecha_generacion,
        'fecha_expiracion': analisis.fecha_expiracion,
        'esta_vigente': analisis.esta_vigente,
        'usuario': analisis.usuario.username if analisis.usuario else None,
    })


def factibilidad_view(request):
    """Vista HTML del módulo de factibilidad"""
    return render(request, 'cobertura/factibilidad.html', {
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY,
    })
