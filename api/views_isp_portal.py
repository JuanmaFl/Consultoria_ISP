from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from .models import ISPUploadToken, CoberturaISP
from .utils import KMZValidator, KMZProcessor
import zipfile


def isp_upload_portal(request, token):
    """
    Portal de upload para ISPs externos (sin autenticación)
    GET /cobertura/isp-upload/<token>/
    """
    # Verificar token
    token_obj = get_object_or_404(ISPUploadToken, token=token)
    
    if not token_obj.is_valid:
        return render(request, 'cobertura/isp_upload_error.html', {
            'error': 'Token inválido o expirado. Contacte al administrador.'
        })
    
    context = {
        'token': token,
        'proveedor': token_obj.proveedor_nombre,
        'archivos_subidos': token_obj.archivos_subidos,
        'ultima_subida': token_obj.ultima_subida,
    }
    
    return render(request, 'cobertura/isp_upload_portal.html', context)


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def isp_upload_kmz(request, token):
    """
    API para que ISPs suban archivos KMZ
    POST /cobertura/api/isp-upload/<token>/
    """
    # Verificar token
    try:
        token_obj = ISPUploadToken.objects.get(token=token)
    except ISPUploadToken.DoesNotExist:
        return Response({
            'error': 'Token no encontrado'
        }, status=404)
    
    if not token_obj.is_valid:
        return Response({
            'error': 'Token inválido o expirado'
        }, status=403)
    
    # Validar archivo
    if 'archivo' not in request.FILES:
        return Response({
            'error': 'No se proporcionó ningún archivo'
        }, status=400)
    
    archivo = request.FILES['archivo']
    
    try:
        # 1. Validaciones básicas
        from rest_framework.exceptions import ValidationError
        KMZValidator.validate_file_extension(archivo.name)
        KMZValidator.validate_file_size(archivo.size)
        
        # 2. El proveedor es el nombre del token
        proveedor = token_obj.proveedor_nombre
        
        # 3. Verificar duplicados
        if KMZProcessor.check_duplicates(archivo.name, proveedor):
            return Response({
                'error': f'El archivo "{archivo.name}" ya existe en la base de datos.',
                'detalle': 'Si necesita reemplazarlo, contacte al administrador.'
            }, status=409)
        
        # 4. Validar estructura ZIP
        archivo.seek(0)
        kml_filename = KMZValidator.validate_zip_structure(archivo)
        
        # 5. Extraer y parsear KML
        archivo.seek(0)
        with zipfile.ZipFile(archivo, 'r') as zip_ref:
            kml_content = zip_ref.read(kml_filename)
        
        geometries = KMZProcessor.parse_kml_content(kml_content)
        
        # 6. Guardar en BD (sin usuario autenticado)
        archivo.seek(0)
        result = KMZProcessor.save_geometries_to_db(
            geometries=geometries,
            archivo_origen=archivo.name,
            proveedor=proveedor,
            usuario=None,  # ISP externo, sin usuario
            archivo_fisico=archivo
        )
        
        # 7. Actualizar estadísticas del token
        token_obj.archivos_subidos += 1
        token_obj.ultima_subida = timezone.now()
        token_obj.save()
        
        # 8. Enviar notificación por email
        try:
            send_notification_email(
                proveedor=proveedor,
                archivo_nombre=archivo.name,
                estadisticas=result
            )
        except Exception as e:
            # No fallar si el email falla
            print(f"Error enviando email: {e}")
        
        # 9. Respuesta exitosa
        return Response({
            'success': True,
            'mensaje': f'Archivo "{archivo.name}" procesado exitosamente',
            'proveedor': proveedor,
            'estadisticas': {
                'total_elementos': result['total_count'],
                'guardados': result['saved_count'],
                'errores': len(result['errors'])
            }
        }, status=201)
    
    except ValidationError as e:
        return Response({
            'error': str(e)
        }, status=400)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return Response({
            'error': 'Error interno al procesar el archivo',
            'detalle': str(e)
        }, status=500)


def send_notification_email(proveedor, archivo_nombre, estadisticas):
    """
    Envía email de notificación cuando un ISP sube un archivo
    """
    subject = f'[Cobertura ISP] Nuevo archivo subido por {proveedor}'
    
    message = f"""
    Un nuevo archivo KMZ ha sido subido al sistema:
    
    Proveedor: {proveedor}
    Archivo: {archivo_nombre}
    Fecha: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}
    
    Estadísticas:
    - Total de elementos: {estadisticas['total_count']}
    - Elementos guardados: {estadisticas['saved_count']}
    - Errores: {len(estadisticas['errors'])}
    
    Puede revisar el archivo en el panel de administración:
    https://86.48.21.76/cobertura/admin/api/coberturaisp/
    """
    
    # Email del administrador (configurable en settings)
    admin_email = getattr(settings, 'ADMIN_EMAIL', 'admin@example.com')
    
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [admin_email],
        fail_silently=True,
    )
