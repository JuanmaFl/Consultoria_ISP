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


from django.contrib.auth.decorators import login_required

@login_required(login_url='/cobertura/login/')
def factibilidad_view(request):
    """Vista HTML del módulo de factibilidad"""
    return render(request, 'cobertura/factibilidad.html', {
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY,
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def exportar_pdf_factibilidad(request):
    """
    Exportar análisis de factibilidad a PDF con texto editado
    POST /api/factibilidad/exportar-pdf/
    Body: { "analisis_id": 1, "texto_editado": "..." }
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from io import BytesIO
    from datetime import datetime
    from django.http import FileResponse

    analisis_id = request.data.get('analisis_id')
    texto_editado = request.data.get('texto_editado', '')

    try:
        analisis = AnalisisFactibilidad.objects.get(id=analisis_id)
    except AnalisisFactibilidad.DoesNotExist:
        return Response({'error': 'Análisis no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter,
                            topMargin=0.75*inch, bottomMargin=0.75*inch,
                            leftMargin=inch, rightMargin=inch)
    elements = []
    styles = getSampleStyleSheet()

    # Estilos
    title_style = ParagraphStyle('T', parent=styles['Heading1'],
        fontSize=20, textColor=colors.HexColor('#1a1a2e'), alignment=TA_CENTER, spaceAfter=6)
    subtitle_style = ParagraphStyle('S', parent=styles['Normal'],
        fontSize=11, textColor=colors.HexColor('#6b7280'), alignment=TA_CENTER, spaceAfter=24)
    section_style = ParagraphStyle('Sec', parent=styles['Heading2'],
        fontSize=13, textColor=colors.HexColor('#1a1a2e'), spaceBefore=16, spaceAfter=8)
    body_style = ParagraphStyle('B', parent=styles['Normal'],
        fontSize=10, leading=16, textColor=colors.HexColor('#374151'), spaceAfter=8)
    mono_style = ParagraphStyle('M', parent=styles['Normal'],
        fontSize=9, fontName='Courier', textColor=colors.HexColor('#6b7280'))

    rec_colors = {
        'alta': '#16a34a', 'media': '#ca8a04',
        'baja': '#dc2626', 'saturada': '#2563eb'
    }
    rec_labels = {
        'alta': 'ALTA FACTIBILIDAD', 'media': 'FACTIBILIDAD MEDIA',
        'baja': 'BAJA FACTIBILIDAD', 'saturada': 'ZONA SATURADA'
    }
    rec = analisis.recomendacion or 'baja'
    rec_color = colors.HexColor(rec_colors.get(rec, '#6b7280'))

    # Título
    elements.append(Paragraph("ANÁLISIS DE FACTIBILIDAD", title_style))
    elements.append(Paragraph("Infraestructura de Fibra Óptica · Colombia", subtitle_style))

    # Header con métricas clave
    header_data = [
        ['Zona analizada', analisis.zona_nombre],
        ['Tipo de análisis', analisis.tipo_zona.capitalize()],
        ['Factibilidad', rec_labels.get(rec, rec.upper())],
        ['Score', f"{analisis.score_factibilidad or '—'}/100"],
        ['ISPs en zona', str(len(analisis.isps_presentes or []))],
        ['Km fibra estimados', f"{analisis.km_fibra_estimados or 0:.1f} km"],
        ['Fecha generación', datetime.fromisoformat(str(analisis.fecha_generacion)).strftime('%d/%m/%Y %H:%M')],
    ]

    if analisis.poblacion_zona:
        header_data.insert(4, ['Población', f"{analisis.poblacion_zona:,} hab."])
    if analisis.hogares_zona:
        header_data.insert(5, ['Hogares', f"{analisis.hogares_zona:,}"])

    header_table = Table(header_data, colWidths=[2.2*inch, 4.3*inch])
    header_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
        ('BACKGROUND', (1, 0), (1, -1), colors.white),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#374151')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('PADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
        ('ROWBACKGROUNDS', (0, 2), (-1, 2), [colors.HexColor('#fef9c3')]),
        ('TEXTCOLOR', (1, 2), (1, 2), rec_color),
        ('FONTNAME', (1, 2), (1, 2), 'Helvetica-Bold'),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 0.2*inch))

    # ISPs presentes
    if analisis.isps_presentes:
        elements.append(Paragraph("ISPs con infraestructura en la zona", section_style))
        isps_texto = ' · '.join(analisis.isps_presentes)
        elements.append(Paragraph(isps_texto, mono_style))
        elements.append(Spacer(1, 0.1*inch))

    # Análisis de IA
    elements.append(Paragraph("Análisis de factibilidad", section_style))
    texto_final = texto_editado if texto_editado else analisis.analisis_texto

    # Limpiar bloques JSON del texto antes de mostrar
    import re
    texto_limpio = re.sub(r'```json.*?```', '', texto_final, flags=re.DOTALL).strip()

    for linea in texto_limpio.split('\n'):
        linea = linea.strip()
        if not linea:
            elements.append(Spacer(1, 0.05*inch))
        elif linea.startswith('#') or (linea.isupper() and len(linea) < 60):
            elements.append(Paragraph(linea.lstrip('#').strip(), section_style))
        else:
            elements.append(Paragraph(
        f"Generado por Sistema de Cobertura ISP · {datetime.now().strftime('%d/%m/%Y %H:%M')} · Documento confidencial",
        footer_style
    ))

    doc.build(elements)
    buffer.seek(0)

    filename = f"factibilidad_{analisis.zona_nombre.replace(' ', '_').replace(',', '')}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return FileResponse(buffer, as_attachment=True, filename=filename)
