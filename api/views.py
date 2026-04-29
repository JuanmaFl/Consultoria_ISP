from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D
from django.contrib.auth import authenticate, login as django_login, logout as django_logout
from django.contrib.auth import get_user_model
from django.shortcuts import render, redirect
from django.conf import settings
import requests
import urllib.parse
from django.http import HttpResponse, FileResponse, JsonResponse
from .models import CoberturaISP
from .serializers import (
    CoberturaISPSerializer,
    ConsultaCoberturaSerializer,
    ResultadoCoberturaSerializer,
    UsuarioSerializer
)
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_ratelimit.decorators import ratelimit
from django.views.decorators.cache import never_cache
Usuario = get_user_model()


class UsuarioViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet para usuarios (solo lectura desde API)"""
    queryset = Usuario.objects.all()
    serializer_class = UsuarioSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def me(self, request):
        """Obtener información del usuario actual"""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)


class CoberturaISPViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet para coberturas ISP"""
    queryset = CoberturaISP.objects.all()
    serializer_class = CoberturaISPSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filtrar por proveedor si se especifica
        proveedor = self.request.query_params.get('proveedor', None)
        if proveedor:
            queryset = queryset.filter(proveedor__icontains=proveedor)

        return queryset


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def consultar_cobertura(request):
    """
    Consultar cobertura en una ubicación específica

    POST /api/consultar-cobertura/
    {
        "latitud": 6.2442,
        "longitud": -75.5812,
        "radio_metros": 1000
    }
    """
    serializer = ConsultaCoberturaSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    latitud = serializer.validated_data['latitud']
    longitud = serializer.validated_data['longitud']
    radio_metros = serializer.validated_data.get('radio_metros', 1000)

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

    # Obtener distancia mínima
    distancia_minima = None
    if coberturas_cercanas.exists():
        distancia_minima = round(coberturas_cercanas.first().distancia, 2)

    # Serializar rutas cercanas agrupadas por tipo
    nodos_cercanos = []
    rutas_cercanas = []
    areas_cercanas = []

    for cobertura in coberturas_cercanas[:50]:  # Aumentar límite para agrupar mejor
        # Detectar tipo de geometría
        geom_type = cobertura.geom.geom_type.upper()

        elemento = {
            'id': cobertura.id,
            'nombre': cobertura.nombre or 'Sin nombre',
            'proveedor': cobertura.proveedor or 'Sin proveedor',
            'distancia_metros': round(cobertura.distancia, 2),
            'archivo_origen': cobertura.archivo_origen
        }

        # Clasificar según tipo
        if 'POINT' in geom_type:
            elemento['tipo_geometria'] = 'nodo'
            elemento['tipo_legible'] = 'Nodo'
            elemento['icono'] = '📍'
            elemento['color'] = '#ef4444'  # Rojo
            nodos_cercanos.append(elemento)
        elif 'LINESTRING' in geom_type:
            elemento['tipo_geometria'] = 'ruta'
            elemento['tipo_legible'] = 'Ruta'
            elemento['icono'] = '🛣️'
            elemento['color'] = '#3b82f6'  # Azul
            rutas_cercanas.append(elemento)
        elif 'POLYGON' in geom_type:
            elemento['tipo_geometria'] = 'area'
            elemento['tipo_legible'] = 'Área'
            elemento['icono'] = '🗺️'
            elemento['color'] = '#10b981'  # Verde
            areas_cercanas.append(elemento)

    resultado = {
        'tiene_cobertura': len(isps_disponibles) > 0,
        'isps_disponibles': isps_disponibles,
        'total_isps': len(isps_disponibles),
        'distancia_minima_metros': distancia_minima,
        'nodos_cercanos': nodos_cercanos,
        'rutas_cercanas': rutas_cercanas,
        'areas_cercanas': areas_cercanas,
        'total_nodos': len(nodos_cercanos),
        'total_rutas': len(rutas_cercanas),
        'total_areas': len(areas_cercanas),
        'total_elementos': len(nodos_cercanos) + len(rutas_cercanas) + len(areas_cercanas)
    }

    resultado_serializer = ResultadoCoberturaSerializer(resultado)
    return Response(resultado_serializer.data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def geocodificar_direccion(request):
    """
    Convertir dirección en coordenadas usando Google Geocoding API

    GET /api/geocodificar/?direccion=Calle 10, Medellín, Colombia
    """
    direccion = request.query_params.get('direccion', '')

    if not direccion:
        return Response(
            {'error': 'Parámetro "direccion" es requerido'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # Usar Google Geocoding API
        url = 'https://maps.googleapis.com/maps/api/geocode/json'
        params = {
            'address': direccion,
            'key': settings.GOOGLE_MAPS_API_KEY,
            'region': 'co',
            'components': 'country:CO'
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()

        if data['status'] != 'OK' or not data.get('results'):
            return Response(
                {'error': 'No se encontraron resultados para la dirección'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Formatear resultados
        ubicaciones = []
        for resultado in data['results'][:5]:
            location = resultado['geometry']['location']
            ubicaciones.append({
                'direccion_completa': resultado.get('formatted_address'),
                'latitud': float(location['lat']),
                'longitud': float(location['lng']),
                'tipo': resultado.get('types', [''])[0] if resultado.get('types') else '',
                'importancia': 1.0
            })

        return Response({'resultados': ubicaciones})

    except requests.exceptions.RequestException as e:
        return Response(
            {'error': f'Error al consultar servicio de geocodificación: {str(e)}'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    except Exception as e:
        return Response(
            {'error': f'Error inesperado: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def estadisticas_cobertura(request):
    """
    Obtener estadísticas generales del sistema

    GET /api/estadisticas/
    """
    total_coberturas = CoberturaISP.objects.count()
    proveedores = CoberturaISP.objects.values_list('proveedor', flat=True).distinct().exclude(proveedor__isnull=True).exclude(proveedor='')
    archivos = CoberturaISP.objects.values_list('archivo_origen', flat=True).distinct().exclude(archivo_origen__isnull=True).exclude(archivo_origen='')

    return Response({
        'total_coberturas': total_coberturas,
        'total_proveedores': len(proveedores),
        'proveedores': list(proveedores),
        'total_archivos_kmz': len(archivos),
        'archivos_kmz': list(archivos)
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_estadisticas(request):
    """
    Dashboard completo con estadísticas y mapa de Colombia

    GET /api/dashboard/
    """
    from django.db.models import Count

    # Estadísticas generales
    total_coberturas = CoberturaISP.objects.count()

    # Por proveedor
    por_proveedor = list(
        CoberturaISP.objects.values('proveedor')
        .annotate(cantidad=Count('id'))
        .order_by('-cantidad')
    )

    # Por tipo de geometría
    por_tipo = []
    for tipo in ['MULTILINESTRING', 'MULTIPOINT', 'MULTIPOLYGON']:
        count = CoberturaISP.objects.filter(geom__isnull=False).extra(
            where=[f"GeometryType(geom) = '{tipo}'"]
        ).count()
        if count > 0:
            tipo_nombre = {
                'MULTILINESTRING': 'Líneas (Rutas)',
                'MULTIPOINT': 'Puntos',
                'MULTIPOLYGON': 'Áreas'
            }
            por_tipo.append({
                'tipo': tipo_nombre.get(tipo, tipo),
                'cantidad': count
            })

    # Por archivo origen
    archivos = list(
        CoberturaISP.objects.values('archivo_origen')
        .annotate(cantidad=Count('id'))
        .order_by('archivo_origen')
    )

    # Zonas con cobertura
    zonas_cobertura = set()
    for archivo in CoberturaISP.objects.values_list('archivo_origen', flat=True).distinct():
        if archivo:
            nombre = archivo.replace('.kmz', '').replace('_', ' ')
            zonas_cobertura.add(nombre)

    return Response({
        'resumen': {
            'total_registros': total_coberturas,
            'total_proveedores': len(por_proveedor),
            'total_archivos_kmz': len(archivos),
            'total_zonas': len(zonas_cobertura)
        },
        'por_proveedor': por_proveedor,
        'por_tipo_geometria': por_tipo,
        'archivos_kmz': archivos,
        'zonas_cobertura': sorted(list(zonas_cobertura))
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generar_reporte_pdf(request):
    """
    Generar reporte ejecutivo en PDF con 3 tipos diferenciados

    POST /api/generar-reporte/
    Body: {
        "tipo": "completo" | "comparativa" | "zona"
    }
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from io import BytesIO
    from datetime import datetime
    from django.db.models import Count

    # Obtener tipo de reporte
    tipo = request.data.get('tipo', 'completo')

    # Crear PDF en memoria
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
    elements = []
    styles = getSampleStyleSheet()

    # Estilos personalizados
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#667eea'),
        alignment=TA_CENTER,
        spaceAfter=30
    )

    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#2c3e50'),
        spaceAfter=12,
        spaceBefore=20
    )

    subsection_style = ParagraphStyle(
        'CustomSubsection',
        parent=styles['Heading3'],
        fontSize=13,
        textColor=colors.HexColor('#34495e'),
        spaceAfter=8,
        spaceBefore=12
    )

    # Estilo para nombres largos en tablas
    nombre_style = ParagraphStyle(
        'NombreISP',
        parent=styles['Normal'],
        fontSize=8,
        leading=10,
        wordWrap='CJK'
    )

    # Datos comunes
    fecha_actual = datetime.now().strftime("%d/%m/%Y %H:%M")
    total_registros = CoberturaISP.objects.count()
    por_proveedor = CoberturaISP.objects.values('proveedor').annotate(
        cantidad=Count('id')
    ).order_by('-cantidad')

    # ===============================================
    # TIPO 1: REPORTE COMPLETO
    # ===============================================
    if tipo == 'completo':
        # Título
        elements.append(Paragraph("REPORTE COMPLETO DE COBERTURA ISP", title_style))
        elements.append(Paragraph(f"Generado: {fecha_actual}", styles['Normal']))
        elements.append(Spacer(1, 0.3*inch))

        # Resumen ejecutivo
        elements.append(Paragraph("RESUMEN EJECUTIVO", subtitle_style))
        resumen_data = [
            ['Métrica', 'Valor'],
            ['Total de Registros', f'{total_registros:,}'],
            ['Proveedores Activos', f'{por_proveedor.count()}'],
            ['Archivos KMZ Procesados', f'{CoberturaISP.objects.values("archivo_origen").distinct().count()}'],
        ]

        resumen_table = Table(resumen_data, colWidths=[3*inch, 2*inch])
        resumen_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ]))
        elements.append(resumen_table)
        elements.append(Spacer(1, 0.3*inch))

        # Distribución por proveedor
        elements.append(Paragraph("DISTRIBUCIÓN POR PROVEEDOR", subtitle_style))
        proveedor_data = [['Proveedor', 'Registros', 'Porcentaje']]
        for p in por_proveedor:
            porcentaje = (p['cantidad'] / total_registros * 100) if total_registros > 0 else 0
            proveedor_nombre = p['proveedor'] or 'Sin proveedor'
            proveedor_cell = Paragraph(proveedor_nombre, nombre_style)
            proveedor_data.append([
                proveedor_cell,
                f"{p['cantidad']:,}",
                f"{porcentaje:.1f}%"
            ])

        proveedor_table = Table(proveedor_data, colWidths=[3*inch, 1.5*inch, 1.5*inch])
        proveedor_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(proveedor_table)
        elements.append(Spacer(1, 0.3*inch))

        # Tipos de geometría
        elements.append(Paragraph("TIPOS DE COBERTURA", subtitle_style))
        tipo_data = [['Tipo', 'Cantidad']]
        for tipo_geom in ['MULTILINESTRING', 'MULTIPOINT', 'MULTIPOLYGON']:
            count = CoberturaISP.objects.filter(geom__isnull=False).extra(
                where=[f"GeometryType(geom) = '{tipo_geom}'"]
            ).count()
            if count > 0:
                tipo_nombre = {
                    'MULTILINESTRING': 'Líneas (Rutas de Fibra)',
                    'MULTIPOINT': 'Puntos (Nodos)',
                    'MULTIPOLYGON': 'Áreas (Zonas)'
                }
                tipo_data.append([tipo_nombre.get(tipo_geom, tipo_geom), f"{count:,}"])

        tipo_table = Table(tipo_data, colWidths=[4*inch, 2*inch])
        tipo_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 11),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
        ]))
        elements.append(tipo_table)

    # ===============================================
    # TIPO 2: COMPARATIVA ISPs
    # ===============================================
    elif tipo == 'comparativa':
        # Título
        elements.append(Paragraph("ANÁLISIS COMPARATIVO ENTRE ISPs", title_style))
        elements.append(Paragraph(f"Generado: {fecha_actual}", styles['Normal']))
        elements.append(Spacer(1, 0.3*inch))

        # Introducción
        intro_text = f"""
        Este reporte presenta un análisis detallado de los {por_proveedor.count()} proveedores de Internet
        registrados en el sistema, comparando su cobertura, infraestructura y presencia en el mercado.
        """
        elements.append(Paragraph(intro_text, styles['Normal']))
        elements.append(Spacer(1, 0.2*inch))

        # Ranking de ISPs
        elements.append(Paragraph("1. RANKING DE PROVEEDORES", subtitle_style))

        ranking_data = [['Posición', 'Proveedor', 'Registros', '% Total', 'Índice']]
        max_registros = por_proveedor.first()['cantidad'] if por_proveedor.exists() else 1

        for idx, p in enumerate(por_proveedor, 1):
            porcentaje = (p['cantidad'] / total_registros * 100) if total_registros > 0 else 0
            indice = (p['cantidad'] / max_registros * 100) if max_registros > 0 else 0

            proveedor_nombre = p['proveedor'] or 'Sin proveedor'
            proveedor_cell = Paragraph(proveedor_nombre, nombre_style)

            ranking_data.append([
                f"#{idx}",
                proveedor_cell,
                f"{p['cantidad']:,}",
                f"{porcentaje:.1f}%",
                f"{indice:.1f}"
            ])

        ranking_table = Table(ranking_data, colWidths=[0.6*inch, 2.6*inch, 1.2*inch, 0.9*inch, 0.9*inch])
        ranking_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(ranking_table)
        elements.append(Spacer(1, 0.3*inch))

        # Análisis de infraestructura por ISP
        elements.append(Paragraph("2. INFRAESTRUCTURA POR PROVEEDOR", subtitle_style))

        infra_data = [['Proveedor', 'Líneas', 'Puntos', 'Áreas', 'Total']]

        for p in por_proveedor:
            proveedor_nombre = p['proveedor'] or 'Sin proveedor'
            proveedor_cell = Paragraph(proveedor_nombre, nombre_style)

            lineas = CoberturaISP.objects.filter(
                proveedor=p['proveedor'],
                geom__isnull=False
            ).extra(where=["GeometryType(geom) = 'MULTILINESTRING'"]).count()

            puntos = CoberturaISP.objects.filter(
                proveedor=p['proveedor'],
                geom__isnull=False
            ).extra(where=["GeometryType(geom) = 'MULTIPOINT'"]).count()

            areas = CoberturaISP.objects.filter(
                proveedor=p['proveedor'],
                geom__isnull=False
            ).extra(where=["GeometryType(geom) = 'MULTIPOLYGON'"]).count()

            infra_data.append([
                proveedor_cell,
                f"{lineas:,}",
                f"{puntos:,}",
                f"{areas:,}",
                f"{p['cantidad']:,}"
            ])

        infra_table = Table(infra_data, colWidths=[2.5*inch, 1*inch, 1*inch, 1*inch, 1*inch])
        infra_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(infra_table)
        elements.append(Spacer(1, 0.3*inch))

        # Análisis competitivo
        elements.append(Paragraph("3. ANÁLISIS COMPETITIVO", subtitle_style))

        if por_proveedor.count() > 0:
            lider = por_proveedor.first()
            lider_nombre = lider['proveedor'] or 'Sin proveedor'
            lider_registros = lider['cantidad']
            lider_porcentaje = (lider_registros / total_registros * 100) if total_registros > 0 else 0

            analisis_text = f"""
            <b>Proveedor Líder:</b> {lider_nombre} con {lider_registros:,} registros ({lider_porcentaje:.1f}% del total).<br/>
            <br/>
            """

            if por_proveedor.count() > 1:
                segundo = por_proveedor[1]
                segundo_nombre = segundo['proveedor'] or 'Sin proveedor'
                segundo_registros = segundo['cantidad']
                diferencia = lider_registros - segundo_registros
                diferencia_porcentual = (diferencia / segundo_registros * 100) if segundo_registros > 0 else 0

                analisis_text += f"""
                <b>Segundo Lugar:</b> {segundo_nombre} con {segundo_registros:,} registros.<br/>
                El líder supera al segundo lugar por {diferencia:,} registros ({diferencia_porcentual:.1f}% más).<br/>
                <br/>
                """

            # Concentración del mercado
            top3_total = sum([p['cantidad'] for p in list(por_proveedor)[:3]])
            concentracion = (top3_total / total_registros * 100) if total_registros > 0 else 0

            analisis_text += f"""
            <b>Concentración del Mercado:</b> Los 3 proveedores principales concentran
            {top3_total:,} registros ({concentracion:.1f}% del total).
            """

            elements.append(Paragraph(analisis_text, styles['Normal']))

    # ===============================================
    # TIPO 3: ANÁLISIS POR ZONA
    # ===============================================
    elif tipo == 'zona':
        # Título
        elements.append(Paragraph("ANÁLISIS DE COBERTURA POR ZONA GEOGRÁFICA", title_style))
        elements.append(Paragraph(f"Generado: {fecha_actual}", styles['Normal']))
        elements.append(Spacer(1, 0.3*inch))

        # Introducción
        intro_text = """
        Este reporte analiza la distribución geográfica de la cobertura, identificando
        las zonas con mayor presencia de proveedores y el nivel de competencia en cada área.
        """
        elements.append(Paragraph(intro_text, styles['Normal']))
        elements.append(Spacer(1, 0.2*inch))

        # Obtener datos por zona (archivo_origen)
        por_zona = list(
            CoberturaISP.objects.values('archivo_origen')
            .annotate(cantidad=Count('id'))
            .order_by('-cantidad')
        )

        # Top 10 zonas
        elements.append(Paragraph("1. TOP 10 ZONAS CON MAYOR COBERTURA", subtitle_style))

        top_zonas_data = [['Posición', 'Zona', 'Registros', '% del Total']]

        for idx, zona in enumerate(por_zona[:10], 1):
            zona_nombre = zona['archivo_origen'].replace('.kmz', '').replace('_', ' ') if zona['archivo_origen'] else 'Sin zona'
            porcentaje = (zona['cantidad'] / total_registros * 100) if total_registros > 0 else 0
            zona_cell = Paragraph(zona_nombre, nombre_style)
            top_zonas_data.append([
                f"#{idx}",
                zona_cell,
                f"{zona['cantidad']:,}",
                f"{porcentaje:.1f}%"
            ])

        top_zonas_table = Table(top_zonas_data, colWidths=[0.6*inch, 3.5*inch, 1.3*inch, 1*inch])
        top_zonas_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(top_zonas_table)
        elements.append(Spacer(1, 0.3*inch))

        # Análisis de competencia por zona
        elements.append(Paragraph("2. ANÁLISIS DE COMPETENCIA POR ZONA", subtitle_style))

        competencia_data = [['Zona', 'ISPs Presentes', 'Tipo Mercado']]

        for zona in por_zona[:15]:  # Top 15 zonas
            zona_nombre = zona['archivo_origen'].replace('.kmz', '').replace('_', ' ') if zona['archivo_origen'] else 'Sin zona'
            zona_cell = Paragraph(zona_nombre, nombre_style)

            # Contar ISPs únicos en esta zona
            isps_en_zona = CoberturaISP.objects.filter(
                archivo_origen=zona['archivo_origen']
            ).values('proveedor').distinct().count()

            # Determinar tipo de mercado
            if isps_en_zona == 1:
                tipo_mercado = 'Monopolio'
            elif isps_en_zona == 2:
                tipo_mercado = 'Duopolio'
            elif isps_en_zona <= 4:
                tipo_mercado = 'Competencia Limitada'
            else:
                tipo_mercado = 'Alta Competencia'

            competencia_data.append([
                zona_cell,
                str(isps_en_zona),
                tipo_mercado
            ])

        competencia_table = Table(competencia_data, colWidths=[3*inch, 1.5*inch, 2*inch])
        competencia_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(competencia_table)
        elements.append(Spacer(1, 0.3*inch))

        # Distribución de ISPs por zona (nueva página)
        elements.append(PageBreak())
        elements.append(Paragraph("3. DISTRIBUCIÓN DE ISPs POR ZONA", subtitle_style))

        # Agrupar zonas por ISP
        distribucion_data = [['Zona', 'Proveedores Presentes']]

        for zona in por_zona[:12]:  # Top 12 zonas
            zona_nombre = zona['archivo_origen'].replace('.kmz', '').replace('_', ' ') if zona['archivo_origen'] else 'Sin zona'
            zona_cell = Paragraph(zona_nombre, nombre_style)

            # Obtener ISPs en esta zona
            isps_list = list(
                CoberturaISP.objects.filter(archivo_origen=zona['archivo_origen'])
                .values_list('proveedor', flat=True)
                .distinct()
                .exclude(proveedor__isnull=True)
                .exclude(proveedor='')
            )

            isps_texto = ', '.join(isps_list) if isps_list else 'Sin proveedor'
            isps_cell = Paragraph(isps_texto, nombre_style)

            distribucion_data.append([
                zona_cell,
                isps_cell
            ])

        distribucion_table = Table(distribucion_data, colWidths=[2.5*inch, 4*inch])
        distribucion_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(distribucion_table)
        elements.append(Spacer(1, 0.3*inch))

        # Resumen de concentración geográfica
        elements.append(Paragraph("4. RESUMEN DE CONCENTRACIÓN GEOGRÁFICA", subtitle_style))

        total_zonas = len(por_zona)
        top5_zonas = sum([z['cantidad'] for z in por_zona[:5]])
        concentracion_geografica = (top5_zonas / total_registros * 100) if total_registros > 0 else 0

        # Contar zonas por tipo de mercado
        monopolios = 0
        competencia_alta = 0

        for zona in por_zona:
            isps_count = CoberturaISP.objects.filter(
                archivo_origen=zona['archivo_origen']
            ).values('proveedor').distinct().count()

            if isps_count == 1:
                monopolios += 1
            elif isps_count >= 4:
                competencia_alta += 1

        resumen_geo_text = f"""
        <b>Total de Zonas Identificadas:</b> {total_zonas}<br/>
        <b>Concentración Top 5:</b> Las 5 zonas principales concentran {top5_zonas:,} registros
        ({concentracion_geografica:.1f}% del total).<br/>
        <br/>
        <b>Distribución de Mercados:</b><br/>
        • Zonas con monopolio (1 ISP): {monopolios}<br/>
        • Zonas con alta competencia (4+ ISPs): {competencia_alta}<br/>
        <br/>
        <b>Oportunidades:</b> {"Se identifican " + str(monopolios) + " zonas con un solo proveedor, " +
        "representando oportunidades de expansión para nuevos operadores." if monopolios > 0 else
        "La mayoría de zonas presenta competencia entre múltiples proveedores."}
        """

        elements.append(Paragraph(resumen_geo_text, styles['Normal']))

    # Footer común para todos los reportes
    elements.append(Spacer(1, 0.5*inch))
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.grey,
        alignment=TA_CENTER
    )
    elements.append(Paragraph("Sistema de Consulta de Cobertura ISP - Reporte Confidencial", footer_style))
    elements.append(Paragraph(f"Tipo de reporte: {tipo.upper()}", footer_style))

    # Generar PDF
    doc.build(elements)

    # Devolver PDF
    buffer.seek(0)
    filename_map = {
        'completo': 'reporte_completo',
        'comparativa': 'comparativa_isps',
        'zona': 'analisis_zona'
    }
    filename = f'{filename_map.get(tipo, "reporte")}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'

    return FileResponse(buffer, as_attachment=True, filename=filename)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def detalle_isp(request, nombre_isp):
    """
    Obtener detalle completo de un ISP específico

    GET /api/detalle-isp/<nombre_isp>/
    """
    from django.db.models import Count, Q
    from urllib.parse import unquote

    # Decodificar el nombre del ISP (por si tiene espacios u otros caracteres)
    nombre_isp = unquote(nombre_isp)

    # Validar que el ISP existe
    if not CoberturaISP.objects.filter(proveedor=nombre_isp).exists():
        return Response(
            {'error': f'ISP "{nombre_isp}" no encontrado'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Total de registros del ISP
    total_registros = CoberturaISP.objects.filter(proveedor=nombre_isp).count()

    # Contar por tipo de geometría
    nodos_count = CoberturaISP.objects.filter(
        proveedor=nombre_isp,
        geom__isnull=False
    ).extra(where=["GeometryType(geom) IN ('POINT', 'MULTIPOINT')"]).count()

    rutas_count = CoberturaISP.objects.filter(
        proveedor=nombre_isp,
        geom__isnull=False
    ).extra(where=["GeometryType(geom) IN ('LINESTRING', 'MULTILINESTRING')"]).count()

    areas_count = CoberturaISP.objects.filter(
        proveedor=nombre_isp,
        geom__isnull=False
    ).extra(where=["GeometryType(geom) IN ('POLYGON', 'MULTIPOLYGON')"]).count()

    # Desglose por zona (archivo_origen)
    zonas = []
    zonas_data = CoberturaISP.objects.filter(
        proveedor=nombre_isp
    ).values('archivo_origen').annotate(
        total=Count('id')
    ).order_by('-total')

    for zona in zonas_data:
        archivo = zona['archivo_origen']
        zona_nombre = archivo.replace('.kmz', '').replace('_', ' ') if archivo else 'Sin zona'

        # Contar por tipo en esta zona
        zona_nodos = CoberturaISP.objects.filter(
            proveedor=nombre_isp,
            archivo_origen=archivo,
            geom__isnull=False
        ).extra(where=["GeometryType(geom) IN ('POINT', 'MULTIPOINT')"]).count()

        zona_rutas = CoberturaISP.objects.filter(
            proveedor=nombre_isp,
            archivo_origen=archivo,
            geom__isnull=False
        ).extra(where=["GeometryType(geom) IN ('LINESTRING', 'MULTILINESTRING')"]).count()

        zona_areas = CoberturaISP.objects.filter(
            proveedor=nombre_isp,
            archivo_origen=archivo,
            geom__isnull=False
        ).extra(where=["GeometryType(geom) IN ('POLYGON', 'MULTIPOLYGON')"]).count()

        # Obtener coordenadas centrales de esta zona para el mapa
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    ST_Y(ST_Centroid(ST_Collect(geom))) as centro_lat,
                    ST_X(ST_Centroid(ST_Collect(geom))) as centro_lng
                FROM cobertura_isp
                WHERE proveedor = %s AND archivo_origen = %s
            """, [nombre_isp, archivo])

            result = cursor.fetchone()
            centroid_data = {
                'centro_lat': result[0] if result else None,
                'centro_lng': result[1] if result else None
            }

        zonas.append({
            'nombre': zona_nombre,
            'archivo_origen': archivo,
            'total_elementos': zona['total'],
            'nodos': zona_nodos,
            'rutas': zona_rutas,
            'areas': zona_areas,
            'centro_lat': float(centroid_data['centro_lat']) if centroid_data['centro_lat'] else None,
            'centro_lng': float(centroid_data['centro_lng']) if centroid_data['centro_lng'] else None
        })

    # Respuesta completa
    return Response({
        'nombre_isp': nombre_isp,
        'resumen': {
            'total_registros': total_registros,
            'total_nodos': nodos_count,
            'total_rutas': rutas_count,
            'total_areas': areas_count,
            'total_zonas': len(zonas)
        },
        'zonas': zonas
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def detalle_kmz(request, archivo_kmz):
    """
    Obtener detalle completo de un archivo KMZ específico

    GET /api/detalle-kmz/<archivo_kmz>/
    """
    from urllib.parse import unquote

    # Decodificar el nombre del archivo
    archivo_kmz = unquote(archivo_kmz)

    # Validar que el archivo existe
    if not CoberturaISP.objects.filter(archivo_origen=archivo_kmz).exists():
        return Response(
            {'error': f'Archivo KMZ "{archivo_kmz}" no encontrado'},
            status=status.HTTP_404_NOT_FOUND
        )

    # Total de registros del archivo
    total_registros = CoberturaISP.objects.filter(archivo_origen=archivo_kmz).count()

    # Obtener proveedor
    proveedor = CoberturaISP.objects.filter(
        archivo_origen=archivo_kmz,
        proveedor__isnull=False
    ).values_list('proveedor', flat=True).first() or 'Sin proveedor'

    # Contar por tipo de geometría
    nodos_count = CoberturaISP.objects.filter(
        archivo_origen=archivo_kmz,
        geom__isnull=False
    ).extra(where=["GeometryType(geom) IN ('POINT', 'MULTIPOINT')"]).count()

    rutas_count = CoberturaISP.objects.filter(
        archivo_origen=archivo_kmz,
        geom__isnull=False
    ).extra(where=["GeometryType(geom) IN ('LINESTRING', 'MULTILINESTRING')"]).count()

    areas_count = CoberturaISP.objects.filter(
        archivo_origen=archivo_kmz,
        geom__isnull=False
    ).extra(where=["GeometryType(geom) IN ('POLYGON', 'MULTIPOLYGON')"]).count()

    # Obtener todos los elementos del archivo
    elementos = []
    registros = CoberturaISP.objects.filter(archivo_origen=archivo_kmz)[:500]  # Límite de 500

    for registro in registros:
        geom_type = registro.geom.geom_type.upper() if registro.geom else 'UNKNOWN'

        # Clasificar tipo
        if 'POINT' in geom_type:
            tipo = 'nodo'
            tipo_legible = 'Nodo'
            icono = '📍'
            color = '#f97316'
        elif 'LINESTRING' in geom_type:
            tipo = 'ruta'
            tipo_legible = 'Ruta'
            icono = '🛣️'
            color = '#3b82f6'
        elif 'POLYGON' in geom_type:
            tipo = 'area'
            tipo_legible = 'Área'
            icono = '🗺️'
            color = '#eab308'
        else:
            tipo = 'otro'
            tipo_legible = 'Otro'
            icono = '❓'
            color = '#6b7280'

        elementos.append({
            'id': registro.id,
            'nombre': registro.nombre or 'Sin nombre',
            'tipo': tipo,
            'tipo_legible': tipo_legible,
            'icono': icono,
            'color': color,
            'geom_type': geom_type
        })

    # Calcular coordenadas centrales para el mapa
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT
                ST_Y(ST_Centroid(ST_Collect(geom))) as centro_lat,
                ST_X(ST_Centroid(ST_Collect(geom))) as centro_lng
            FROM cobertura_isp
            WHERE archivo_origen = %s
        """, [archivo_kmz])

        result = cursor.fetchone()
        centro_lat = result[0] if result else None
        centro_lng = result[1] if result else None

    # Respuesta completa
    return Response({
        'archivo_kmz': archivo_kmz,
        'nombre_legible': archivo_kmz.replace('.kmz', '').replace('_', ' '),
        'proveedor': proveedor,
        'resumen': {
            'total_registros': total_registros,
            'total_nodos': nodos_count,
            'total_rutas': rutas_count,
            'total_areas': areas_count
        },
        'elementos': elementos,
        'centro_lat': centro_lat,
        'centro_lng': centro_lng
    })

# ===============================================
# FASE 4: VISTAS DE UPLOAD KMZ
# ===============================================


def upload_view(request):
    """Vista del template de upload de archivos KMZ"""
    return render(request, 'cobertura/upload.html')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_kmz(request):
    """
    Endpoint para subir y procesar archivos KMZ

    POST /api/upload-kmz/
    Form-data:
        - archivo: archivo KMZ
    """
    from .utils import KMZValidator, KMZProcessor
    from rest_framework.exceptions import ValidationError
    import zipfile

    # Validar que se subió un archivo
    if 'archivo' not in request.FILES:
        return Response(
            {'error': 'No se proporcionó ningún archivo'},
            status=status.HTTP_400_BAD_REQUEST
        )

    archivo = request.FILES['archivo']

    try:
        # 1. Validaciones básicas
        KMZValidator.validate_file_extension(archivo.name)
        KMZValidator.validate_file_size(archivo.size)

        # 2. Detectar proveedor del nombre del archivo
        proveedor = KMZProcessor.extract_provider_from_filename(archivo.name)

        # 3. Verificar duplicados
        if KMZProcessor.check_duplicates(archivo.name, proveedor):
            return Response(
                {
                    'error': f'El archivo "{archivo.name}" ya existe en la base de datos para el proveedor {proveedor}.',
                    'detalle': 'Por favor, elimina el archivo existente desde el panel de administración antes de subir uno nuevo.'
                },
                status=status.HTTP_409_CONFLICT
            )

        # 4. Validar estructura ZIP y obtener archivo KML
        archivo.seek(0)  # Resetear puntero
        kml_filename = KMZValidator.validate_zip_structure(archivo)

        # 5. Extraer y parsear contenido KML
        archivo.seek(0)  # Resetear puntero
        with zipfile.ZipFile(archivo, 'r') as zip_ref:
            kml_content = zip_ref.read(kml_filename)

        geometries = KMZProcessor.parse_kml_content(kml_content)

        # 6. Guardar archivo físico y geometrías en BD (transacción atómica)
        archivo.seek(0)  # Resetear puntero para guardarlo
        result = KMZProcessor.save_geometries_to_db(
            geometries=geometries,
            archivo_origen=archivo.name,
            proveedor=proveedor,
            usuario=request.user,
            archivo_fisico=archivo  # Django guardará el archivo automáticamente
        )

        # 7. Respuesta exitosa
        return Response({
            'success': True,
            'mensaje': f'Archivo "{archivo.name}" procesado exitosamente',
            'proveedor': proveedor,
            'estadisticas': {
                'total_elementos': result['total_count'],
                'guardados': result['saved_count'],
                'errores': len(result['errors'])
            },
            'detalles': result['errors'] if result['errors'] else []
        }, status=status.HTTP_201_CREATED)

    except ValidationError as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()

        return Response(
            {
                'error': 'Error interno al procesar el archivo',
                'detalle': str(e)
            },
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

    # Obtener archivos únicos con estadísticas
    archivos = CoberturaISP.objects.values('archivo_origen', 'proveedor').annotate(
        total_elementos=Count('id'),
        fecha_subida=Max('fecha_importacion')
    ).order_by('-fecha_subida')

    # Formatear respuesta
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

# ===============================================
# VISTAS DE TEMPLATES
# ===============================================

from django.contrib.auth import authenticate, login as django_login

def login_view(request):
    from django_ratelimit.exceptions import Ratelimited
    
    # Verificar si está bloqueado
    was_limited = getattr(request, 'limited', False)
    if was_limited:
        return JsonResponse({
            'error': 'Demasiados intentos. Espera 1 minuto.'
        }, status=429)

    """Vista de login - Con integración 2FA y sesión Django"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # HACER LOGIN DE SESIÓN DJANGO (no JWT)
            django_login(request, user)
            
            # Verificar si tiene 2FA configurado
            from django_otp.plugins.otp_totp.models import TOTPDevice
            has_2fa = TOTPDevice.objects.filter(user=user, confirmed=True).exists()
            
            if has_2fa:
                # Marcar que necesita verificación 2FA
                request.session['otp_verified'] = False
                request.session['pending_2fa'] = True
                
                # Redirigir a verificación 2FA
                next_url = request.GET.get('next', '/cobertura/mapa/')
                return redirect(f'/cobertura/2fa/verify-login/?next={next_url}')
            else:
                # Login normal sin 2FA
                request.session['otp_verified'] = True
                
                next_url = request.GET.get('next', '/cobertura/mapa/')
                return redirect(next_url)
        else:
            # Credenciales inválidas
            return render(request, 'cobertura/login.html', {
                'error': 'Usuario o contraseña incorrectos'
            })
    
    return render(request, 'cobertura/login.html')


def logout_view(request):
    """Vista de logout - Cerrar sesión"""
    django_logout(request)
    return redirect('/cobertura/login/')

def mapa_view(request):
    """Vista del mapa interactivo"""
    return render(request, 'cobertura/mapa.html', {
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY
    })

def dashboard_view(request):
    """Vista del dashboard de estadísticas"""
    return render(request, 'cobertura/dashboard.html', {
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY
    })
    

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def listar_proveedores(request):
    """
    Listar todos los proveedores únicos en el sistema
    
    GET /api/listar-proveedores/
    """
    proveedores = list(
        CoberturaISP.objects.values_list('proveedor', flat=True)
        .distinct()
        .exclude(proveedor__isnull=True)
        .exclude(proveedor='')
        .order_by('proveedor')
    )
    
    return Response({
        'total': len(proveedores),
        'proveedores': proveedores
    })
    
import urllib.parse
from django.http import JsonResponse

# ===============================================
# DELETE KMZ - SPRINT 2
# ===============================================

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_kmz(request, archivo_nombre):
    """
    Eliminar archivo KMZ y todos sus registros asociados
    
    DELETE /api/delete-kmz/<archivo_nombre>/
    """
    from urllib.parse import unquote
    from django.db import transaction
    
    # Decodificar nombre del archivo
    archivo_nombre = unquote(archivo_nombre)
    
    # Verificar que el archivo existe
    registros = CoberturaISP.objects.filter(archivo_origen=archivo_nombre)
    
    if not registros.exists():
        return Response({
            'error': f'Archivo "{archivo_nombre}" no encontrado'
        }, status=status.HTTP_404_NOT_FOUND)
    
    # Contar registros antes de eliminar
    total_registros = registros.count()
    proveedor = registros.first().proveedor if registros.first() else 'Desconocido'
    
    try:
        # Eliminar todos los registros asociados (transacción atómica)
        with transaction.atomic():
            registros.delete()
        
        return Response({
            'success': True,
            'mensaje': f'Archivo "{archivo_nombre}" eliminado exitosamente',
            'detalles': {
                'archivo': archivo_nombre,
                'proveedor': proveedor,
                'registros_eliminados': total_registros
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        return Response({
            'error': 'Error al eliminar el archivo',
            'detalle': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)