from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.core.files.base import ContentFile
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from .models import BulkQueryJob, CoberturaISP
from .utils_csv import CSVProcessor
import requests
from django.conf import settings


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def bulk_query_view(request):
    """
    Vista del template de consulta masiva
    GET /cobertura/bulk-query/
    """
    # Obtener historial de jobs del usuario
    jobs_recientes = BulkQueryJob.objects.filter(
        usuario=request.user
    ).order_by('-fecha_creacion')[:10]
    
    context = {
        'jobs_recientes': jobs_recientes
    }
    
    return render(request, 'cobertura/bulk_query.html', context)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_bulk_query(request):
    """
    Procesa archivo CSV para consulta masiva
    POST /cobertura/api/bulk-query/upload/
    """
    if 'archivo' not in request.FILES:
        return Response({
            'error': 'No se proporcionó ningún archivo'
        }, status=400)
    
    archivo = request.FILES['archivo']
    
    # Validar extensión
    if not archivo.name.lower().endswith('.csv'):
        return Response({
            'error': 'Solo se permiten archivos CSV'
        }, status=400)
    
    # Validar tamaño (10MB max)
    if archivo.size > 10 * 1024 * 1024:
        return Response({
            'error': 'Archivo muy grande (máximo 10MB)'
        }, status=400)
    
    try:
        # Parsear CSV
        formato, registros = CSVProcessor.parse_csv(archivo)
        
        # Filtrar solo registros válidos
        registros_validos = [r for r in registros if r.get('tipo') != 'error']
        total_registros = len(registros_validos)
        
        if total_registros == 0:
            return Response({
                'error': 'No se encontraron registros válidos en el archivo'
            }, status=400)
        
        # Crear job
        job = BulkQueryJob.objects.create(
            usuario=request.user,
            archivo_entrada=archivo,
            total_registros=total_registros,
            status='pending'
        )
        
        # Siempre asincrono: procesar_jobs_pendientes lo toma por cron
        tiempo_estimado = total_registros * 0.4

        return Response({
            'success': True,
            'tipo': 'asincrono',
            'job_id': job.id,
            'total_registros': total_registros,
            'tiempo_estimado_segundos': int(tiempo_estimado),
            'tiempo_estimado_minutos': max(1, round(tiempo_estimado / 60)),
            'mensaje': 'El archivo esta en cola de procesamiento.'
        }, status=202)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({
            'error': 'Error al procesar el archivo',
            'detalle': str(e)
        }, status=500)


def procesar_consultas_sincronico(registros, formato):
    """
    Procesa consultas de forma síncrona
    """
    resultados = []
    
    for registro in registros:
        try:
            # Obtener coordenadas
            if registro['tipo'] == 'coordenada':
                latitud = registro['latitud']
                longitud = registro['longitud']
                coords_str = f"{latitud},{longitud}"
            else:  # dirección
                # Geocodificar dirección
                coords = geocodificar_direccion(registro['direccion'])
                if not coords:
                    resultados.append({
                        'entrada_original': registro['entrada_original'],
                        'tiene_cobertura': False,
                        'isps_disponibles': [],
                        'distancia_minima_metros': 'N/A',
                        'total_isps': 0,
                        'coordenadas_consultadas': 'Error al geocodificar'
                    })
                    continue
                
                latitud = coords['latitud']
                longitud = coords['longitud']
                coords_str = f"{latitud},{longitud}"
            
            # Consultar cobertura
            resultado_cobertura = consultar_cobertura_punto(latitud, longitud)
            
            resultados.append({
                'entrada_original': registro['entrada_original'],
                'tiene_cobertura': resultado_cobertura['tiene_cobertura'],
                'isps_disponibles': resultado_cobertura['isps_disponibles'],
                'distancia_minima_metros': resultado_cobertura['distancia_minima_metros'],
                'total_isps': resultado_cobertura['total_isps'],
                'coordenadas_consultadas': coords_str
            })
        
        except Exception as e:
            print(f"Error procesando registro: {e}")
            resultados.append({
                'entrada_original': registro.get('entrada_original', ''),
                'tiene_cobertura': False,
                'isps_disponibles': [],
                'distancia_minima_metros': 'Error',
                'total_isps': 0,
                'coordenadas_consultadas': 'Error en procesamiento'
            })
    
    return resultados


def geocodificar_direccion(direccion):
    """
    Geocodifica una dirección usando Google Maps API
    """
    try:
        url = 'https://maps.googleapis.com/maps/api/geocode/json'
        params = {
            'address': direccion,
            'key': settings.GOOGLE_MAPS_API_KEY,
            'region': 'co',
            'components': 'country:CO'
        }
        
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if data['status'] == 'OK' and data.get('results'):
            location = data['results'][0]['geometry']['location']
            return {
                'latitud': float(location['lat']),
                'longitud': float(location['lng'])
            }
    except Exception as e:
        print(f"Error geocodificando {direccion}: {e}")
    
    return None


def consultar_cobertura_punto(latitud, longitud, radio_metros=1000):
    """
    Consulta cobertura en un punto específico
    """
    # Crear punto de consulta
    punto = Point(longitud, latitud, srid=4326)
    
    # Buscar coberturas dentro del radio
    coberturas_cercanas = CoberturaISP.objects.extra(
        where=[
            "ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)"
        ],
        params=[longitud, latitud, radio_metros]
    ).extra(
        select={
            'distancia': "ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography)"
        },
        select_params=[longitud, latitud]
    ).order_by('distancia')
    
    # Obtener ISPs únicos
    isps_disponibles = list(
        coberturas_cercanas.values_list('proveedor', flat=True)
        .distinct()
        .exclude(proveedor__isnull=True)
        .exclude(proveedor='')
    )
    
    # Distancia mínima
    distancia_minima = None
    if coberturas_cercanas.exists():
        distancia_minima = round(coberturas_cercanas.first().distancia, 2)
    
    return {
        'tiene_cobertura': len(isps_disponibles) > 0,
        'isps_disponibles': isps_disponibles,
        'total_isps': len(isps_disponibles),
        'distancia_minima_metros': distancia_minima if distancia_minima is not None else 'N/A'
    }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_job_status(request, job_id):
    """
    Verifica el estado de un job de consulta masiva
    GET /cobertura/api/bulk-query/status/<job_id>/
    """
    try:
        job = BulkQueryJob.objects.get(id=job_id, usuario=request.user)
        
        return Response({
            'job_id': job.id,
            'status': job.status,
            'total_registros': job.total_registros,
            'registros_procesados': job.registros_procesados,
            'progreso_porcentaje': job.progreso_porcentaje,
            'archivo_salida_url': job.archivo_salida.url if job.archivo_salida else None,
            'error': job.error_mensaje
        })
    except BulkQueryJob.DoesNotExist:
        return Response({
            'error': 'Job no encontrado'
        }, status=404)
