from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import render
from django.http import FileResponse
from .models import CoberturaISP


def upload_view(request):
    """Vista del template de upload de archivos KMZ"""
    return render(request, 'cobertura/upload.html')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_kmz(request):
    """
    Endpoint para subir y procesar archivos KMZ
    POST /api/upload-kmz/
    """
    from .utils import KMZValidator, KMZProcessor
    from rest_framework.exceptions import ValidationError
    import zipfile

    if 'archivo' not in request.FILES:
        return Response(
            {'error': 'No se proporcionó ningún archivo'},
            status=status.HTTP_400_BAD_REQUEST
        )

    archivo = request.FILES['archivo']

    try:
        KMZValidator.validate_file_extension(archivo.name)
        KMZValidator.validate_file_size(archivo.size)

        proveedor = KMZProcessor.extract_provider_from_filename(archivo.name)

        if KMZProcessor.check_duplicates(archivo.name, proveedor):
            return Response(
                {
                    'error': f'El archivo "{archivo.name}" ya existe en la base de datos.',
                    'detalle': 'Elimina el archivo existente antes de subir uno nuevo.'
                },
                status=status.HTTP_409_CONFLICT
            )

        archivo.seek(0)
        kml_filename = KMZValidator.validate_zip_structure(archivo)

        archivo.seek(0)
        with zipfile.ZipFile(archivo, 'r') as zip_ref:
            kml_content = zip_ref.read(kml_filename)

        geometries = KMZProcessor.parse_kml_content(kml_content)

        archivo.seek(0)
        result = KMZProcessor.save_geometries_to_db(
            geometries=geometries,
            archivo_origen=archivo.name,
            proveedor=proveedor,
            usuario=request.user,
            archivo_fisico=archivo
        )

        return Response({
            'success': True,
            'mensaje': f'Archivo "{archivo.name}" procesado exitosamente',
            'proveedor': proveedor,
            'estadisticas': {
                'total_elementos': result['total_count'],
                'guardados': result['saved_count'],
                'errores': len(result['errors'])
            }
        }, status=status.HTTP_201_CREATED)

    except ValidationError as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response(
            {'error': 'Error interno al procesar el archivo', 'detalle': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def listar_archivos_kmz(request):
    """
    Listar todos los archivos KMZ únicos en el sistema
    GET /api/listar-kmz/
    """
    from django.db.models import Count, Max

    archivos = CoberturaISP.objects.values('archivo_origen', 'proveedor').annotate(
        total_elementos=Count('id'),
        fecha_subida=Max('fecha_importacion')
    ).order_by('-fecha_subida')

    archivos_list = []
    for archivo in archivos:
        archivos_list.append({
            'nombre': archivo['archivo_origen'],
            'proveedor': archivo['proveedor'] or 'Sin proveedor',
            'total_elementos': archivo['total_elementos'],
            'fecha_subida': archivo['fecha_subida']
        })

    return Response({
        'total_archivos': len(archivos_list),
        'archivos': archivos_list
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def descargar_kmz(request, archivo_id):
    """Descargar archivo KMZ específico"""
    from django.shortcuts import get_object_or_404

    archivo = get_object_or_404(CoberturaISP, id=archivo_id)
    response = FileResponse(archivo.archivo_fisico.open('rb'))
    response['Content-Disposition'] = f'attachment; filename="{archivo.archivo_fisico.name}"'
    return response


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def detalle_kmz(request, archivo_nombre):
    """Obtener detalles de un archivo KMZ"""
    from urllib.parse import unquote

    archivo_nombre = unquote(archivo_nombre)

    if not CoberturaISP.objects.filter(archivo_origen=archivo_nombre).exists():
        return Response(
            {'error': f'Archivo "{archivo_nombre}" no encontrado'},
            status=status.HTTP_404_NOT_FOUND
        )

    elementos = CoberturaISP.objects.filter(archivo_origen=archivo_nombre)

    return Response({
        'archivo': archivo_nombre,
        'total_elementos': elementos.count(),
        'proveedores': list(elementos.values_list('proveedor', flat=True).distinct()),
    })