import os
import requests
import zipfile
from io import BytesIO
from datetime import datetime
from collections import OrderedDict

# Django Core
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.http import FileResponse, JsonResponse
from django.contrib.auth import authenticate, login as django_login, logout as django_logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q

# Django GIS (GeoDjango)
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D

# Django REST Framework
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from rest_framework.exceptions import ValidationError

# Local Apps (Models & Serializers)
from .models import CoberturaISP
from .serializers import (
    UsuarioSerializer, 
    RegistroUsuarioSerializer,
    CoberturaISPSerializer,
    ConsultaCoberturaSerializer,
    ResultadoCoberturaSerializer,
    ResultadoBusquedaDireccionSerializer
)

# Definir el modelo de usuario actual
Usuario = get_user_model()
# =============================================================================
# VIEWSET DE USUARIOS (lectura desde API)
# =============================================================================

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

# ESTA ES LA CLASE QUE FALTABA Y CAUSABA EL ERROR:
class CoberturaISPViewSet(viewsets.ModelViewSet):
    """ViewSet para el CRUD de coberturas ISP"""
    queryset = CoberturaISP.objects.all()
    serializer_class = CoberturaISPSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        proveedor = self.request.query_params.get('proveedor', None)
        if proveedor:
            queryset = queryset.filter(proveedor__icontains=proveedor)
        return queryset
# =============================================================================
# VISTAS DE LOGIN / LOGOUT (sesión Django)
# =============================================================================

def login_view(request):
    """Vista de login con sesión Django"""
    if request.user.is_authenticated:
        return redirect('/cobertura/mapa/')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            django_login(request, user)
            next_url = request.GET.get('next', '/cobertura/login/')
            return redirect(next_url)
        else:
            return render(request, 'cobertura/login.html', {
                'error': 'Usuario o contraseña incorrectos'
            })

    return render(request, 'cobertura/login.html')


def logout_view(request):
    """Vista de logout - Cerrar sesión"""
    django_logout(request)
    return redirect('/cobertura/login/')


# =============================================================================
# VISTA DE REGISTRO (template)
# =============================================================================

def registro_view(request):
    """Vista de registro de nuevos usuarios"""
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        password2 = request.POST.get('password2')

        # Validaciones
        errors = []

        if not username or not email or not password:
            errors.append('Todos los campos son obligatorios.')

        if password != password2:
            errors.append('Las contraseñas no coinciden.')

        if len(password) < 8:
            errors.append('La contraseña debe tener al menos 8 caracteres.')

        if Usuario.objects.filter(username=username).exists():
            errors.append('Este nombre de usuario ya existe.')

        if Usuario.objects.filter(email=email).exists():
            errors.append('Este email ya está registrado.')

        if errors:
            return render(request, 'cobertura/registro.html', {
                'errors': errors,
                'username': username,
                'email': email,
            })

        # Crear usuario
        user = Usuario.objects.create_user(
            username=username,
            email=email,
            password=password,
        )

        return redirect('/cobertura/login/')

    return render(request, 'cobertura/registro.html')


# =============================================================================
# API ENDPOINTS - REGISTRO
# =============================================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def api_registro_usuario(request):
    """Endpoint para registrar nuevo usuario"""
    serializer = RegistroUsuarioSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user = Usuario.objects.create_user(
        username=serializer.validated_data['username'],
        email=serializer.validated_data['email'],
        password=serializer.validated_data['password'],
    )

    return Response({
        'mensaje': 'Usuario registrado exitosamente.',
        'usuario': UsuarioSerializer(user).data,
    }, status=status.HTTP_201_CREATED)


# =============================================================================
# API ENDPOINTS - CRUD DE USUARIOS (Solo Admin)
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def listar_usuarios(request):
    """Listar todos los usuarios (solo admin)"""
    if not request.user.is_staff:
        return Response(
            {'error': 'No tienes permisos para realizar esta acción.'},
            status=status.HTTP_403_FORBIDDEN
        )

    usuarios = Usuario.objects.all()
    serializer = UsuarioSerializer(usuarios, many=True)
    return Response(serializer.data)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def editar_usuario(request, usuario_id):
    """Editar usuario específico (solo admin)"""
    if not request.user.is_staff:
        return Response(
            {'error': 'No tienes permisos para realizar esta acción.'},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        usuario = Usuario.objects.get(id=usuario_id)
    except Usuario.DoesNotExist:
        return Response(
            {'error': 'Usuario no encontrado.'},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = UsuarioSerializer(usuario, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    serializer.save()
    return Response({
        'mensaje': 'Usuario actualizado exitosamente.',
        'usuario': serializer.data,
    })


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def eliminar_usuario(request, usuario_id):
    """Eliminar usuario (solo admin)"""
    if not request.user.is_staff:
        return Response(
            {'error': 'No tienes permisos para realizar esta acción.'},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        usuario = Usuario.objects.get(id=usuario_id)
    except Usuario.DoesNotExist:
        return Response(
            {'error': 'Usuario no encontrado.'},
            status=status.HTTP_404_NOT_FOUND
        )

    if usuario.is_superuser:
        return Response(
            {'error': 'No se puede eliminar un superusuario.'},
            status=status.HTTP_403_FORBIDDEN
        )

    usuario.delete()
    return Response({
        'mensaje': 'Usuario eliminado exitosamente.',
    }, status=status.HTTP_200_OK)
    
def mapa_view(request):
    """Vista del mapa interactivo"""
    return render(request, 'cobertura/mapa.html', {
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY
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



def _agrupar_por_tipo(coberturas):
    nodos, rutas, areas = [], [], []
    for cobertura in coberturas:
        geom_type = cobertura.geom.geom_type.upper()
        
        # Extraer el valor numérico de la distancia de forma segura
        dist_val = 0
        if hasattr(cobertura, 'distancia'):
            # Si es un objeto Distance, usamos .m (metros)
            try:
                dist_val = round(cobertura.distancia.m, 2)
            except AttributeError:
                dist_val = round(float(cobertura.distancia), 2)

        item = {
            "id": cobertura.id,
            "nombre": cobertura.nombre or "Sin nombre",
            "proveedor": cobertura.proveedor or "Sin proveedor",
            "distancia_metros": dist_val,
            "archivo_origen": cobertura.archivo_origen,
        }
        
        if "POINT" in geom_type: nodos.append(item)
        elif "LINESTRING" in geom_type: rutas.append(item)
        elif "POLYGON" in geom_type: areas.append(item)
        
    return nodos, rutas, areas

def _consultar_por_coordenadas(latitud, longitud, radio_metros):
    try:
        # Convertir a float por seguridad
        lat = float(latitud)
        lng = float(longitud)
        
        punto_consulta = Point(lng, lat, srid=4326)

        # --- AJUSTE PARA SPATIALITE ---
        # 1 grado aprox = 111,111 metros. 
        # Convertimos el radio de metros a grados decimales (aprox)
        radio_en_grados = float(radio_metros) / 111111.0

        # Usamos __dwithin con grados decimales (lo que SpatiaLite exige)
        # Luego usamos Distance para obtener los metros exactos
        coberturas_cercanas = CoberturaISP.objects.filter(
            geom__dwithin=(punto_consulta, radio_en_grados)
        ).annotate(
            distancia=Distance('geom', punto_consulta)
        ).order_by('distancia')

        # Convertir QuerySet a lista de proveedores únicos
        isps_qs = coberturas_cercanas.values_list("proveedor", flat=True).distinct()
        isps_disponibles = [str(x) for x in isps_qs if x]

        distancia_minima = None
        if coberturas_cercanas.exists():
            primera = coberturas_cercanas.first()
            # Extraemos el valor flotante de la distancia
            if hasattr(primera, 'distancia') and primera.distancia is not None:
                # GeoDjango Distance object -> metros
                try:
                    distancia_minima = round(primera.distancia.m, 2)
                except AttributeError:
                    distancia_minima = round(float(primera.distancia), 2)

        # Agrupar elementos para el panel lateral
        nodos, rutas, areas = _agrupar_por_tipo(coberturas_cercanas[:100])

        # Al final de _consultar_por_coordenadas, dentro del return:
        return {
            "tiene_cobertura": len(isps_disponibles) > 0,
            "isps_disponibles": isps_disponibles,
            "total_isps": len(isps_disponibles),
            "distancia_minima_metros": distancia_minima,
            "nodos_cercanos": nodos,
            "rutas_cercanas": rutas,
            "areas_cercanas": areas,
            # Agregamos estos campos para que el Serializer no explote:
            "total_nodos": len(nodos),
            "total_rutas": len(rutas),
            "total_areas": len(areas),
            "total_elementos": len(nodos) + len(rutas) + len(areas)
        }
        
    except Exception as e:
        print(f"\n--- ERROR EN CONSULTA ---")
        import traceback
        traceback.print_exc()
        return {"error": str(e), "tiene_cobertura": False}
    
def _geocodificar_con_google(direccion):
    api_key = getattr(settings, "GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        return None, Response(
            {"error": "GOOGLE_MAPS_API_KEY no esta configurada"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    try:
        response = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={
                "address": direccion,
                "key": api_key,
                "region": "co",
                "components": "country:CO",
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("status") != "OK" or not data.get("results"):
            return None, Response(
                {"error": "No se encontraron resultados para la direccion"},
                status=status.HTTP_404_NOT_FOUND,
            )

        location = data["results"][0]["geometry"]["location"]
        return {
            "direccion_completa": data["results"][0].get("formatted_address", direccion),
            "latitud": float(location["lat"]),
            "longitud": float(location["lng"]),
        }, None
    except requests.exceptions.RequestException as exc:
        return None, Response(
            {"error": f"Error al consultar geocodificacion: {exc}"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def consultar_cobertura(request):
    serializer = ConsultaCoberturaSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    resultado = _consultar_por_coordenadas(
        latitud=serializer.validated_data["latitud"],
        longitud=serializer.validated_data["longitud"],
        radio_metros=serializer.validated_data.get("radio_metros", 1000),
    )
    return Response(ResultadoCoberturaSerializer(resultado).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def geocodificar_direccion(request):
    direccion = request.query_params.get("direccion", "").strip()
    if not direccion:
        return Response(
            {"error": 'Parametro "direccion" es requerido'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    geocodificada, error_response = _geocodificar_con_google(direccion)
    if error_response:
        return error_response

    return Response({"resultados": [geocodificada]})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def buscar_cobertura_por_direccion(request):
    """
    GET /api/buscar-cobertura/?direccion=Calle 10 Medellin
    """

    direccion = request.query_params.get("direccion", "").strip()
    try:
        radio_metros = int(request.query_params.get("radio_metros", 1000))
    except (TypeError, ValueError):
        return Response(
            {"error": 'Parametro "radio_metros" debe ser numerico'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not direccion:
        return Response(
            {"error": 'Parametro "direccion" es requerido'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    geocodificada, error_response = _geocodificar_con_google(direccion)
    if error_response:
        return error_response

    resultado = _consultar_por_coordenadas(
        latitud=geocodificada["latitud"],
        longitud=geocodificada["longitud"],
        radio_metros=radio_metros,
    )

    elementos = resultado["nodos_cercanos"] + resultado["rutas_cercanas"] + resultado["areas_cercanas"]

    respuesta = {
        "direccion": geocodificada["direccion_completa"],
        "hay_cobertura": resultado["tiene_cobertura"],
        "isps_disponibles": resultado["isps_disponibles"],
        "total_isps": resultado["total_isps"],
        "elementos": elementos,
    }

    return Response(ResultadoBusquedaDireccionSerializer(respuesta).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def filtrar_por_isp(request, nombre_isp):
    """
    GET /api/filtrar-isp/<nombre_isp>/
    """

    registros = (
        CoberturaISP.objects.filter(proveedor__iexact=nombre_isp)
        .exclude(geom__isnull=True)
        .order_by("id")[:500]
    )

    elementos = []
    for item in registros:
        geom_type = item.geom.geom_type.upper()
        tipo = "otro"
        if "POINT" in geom_type:
            tipo = "nodo"
        elif "LINESTRING" in geom_type:
            tipo = "ruta"
        elif "POLYGON" in geom_type:
            tipo = "area"

        elementos.append(
            OrderedDict(
                {
                    "id": item.id,
                    "nombre": item.nombre,
                    "proveedor": item.proveedor,
                    "tipo_geometria": tipo,
                    "archivo_origen": item.archivo_origen,
                }
            )
        )

    return Response(
        {
            "isp": nombre_isp,
            "total": len(elementos),
            "elementos": elementos,
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def estadisticas_cobertura(request):
    """
    GET /api/estadisticas/
    """

    total_coberturas = CoberturaISP.objects.count()
    proveedores = list(
        CoberturaISP.objects.values_list("proveedor", flat=True)
        .distinct()
        .exclude(proveedor__isnull=True)
        .exclude(proveedor="")
    )
    archivos_kmz = list(
        CoberturaISP.objects.values_list("archivo_origen", flat=True)
        .distinct()
        .exclude(archivo_origen__isnull=True)
        .exclude(archivo_origen="")
    )

    return Response(
        {
            "total_coberturas": total_coberturas,
            "total_proveedores": len(proveedores),
            "proveedores": proveedores,
            "archivos_kmz": len(archivos_kmz),
        }
    )


@login_required
def dashboard_view(request):
    return render(request, "cobertura/dashboard.html")

# =============================================================================
# VISTAS ADICIONALES (DETALLES Y UPLOAD)
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def detalle_isp(request, nombre_isp):
    """Obtener resumen de un ISP específico"""
    from urllib.parse import unquote
    nombre = unquote(nombre_isp)
    
    elementos = CoberturaISP.objects.filter(proveedor__iexact=nombre)
    if not elementos.exists():
        return Response({"error": "ISP no encontrado"}, status=404)

    return Response({
        "isp": nombre,
        "total_registros": elementos.count(),
        "archivos": list(elementos.values_list('archivo_origen', flat=True).distinct())
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def upload_kmz(request):
    """
    Endpoint real para procesar archivos KMZ/KML
    """
    from .utils import KMZValidator, KMZProcessor
    import zipfile

    if 'archivo' not in request.FILES:
        return Response({'error': 'No se proporcionó ningún archivo'}, status=400)

    archivo = request.FILES['archivo']

    try:
        # 1. Validaciones básicas
        KMZValidator.validate_file_extension(archivo.name)
        KMZValidator.validate_file_size(archivo.size)

        # 2. Detectar proveedor
        proveedor = KMZProcessor.extract_provider_from_filename(archivo.name)

        # 3. Evitar duplicados
        if KMZProcessor.check_duplicates(archivo.name, proveedor):
            return Response({
                'error': f'El archivo "{archivo.name}" ya fue procesado anteriormente.',
                'detalle': 'Si deseas actualizarlo, elimínalo primero desde el panel de administración.'
            }, status=409)

        # 4. Leer contenido (maneja KMZ como ZIP o KML directo)
        archivo.seek(0)
        if archivo.name.lower().endswith('.kmz'):
            kml_filename = KMZValidator.validate_zip_structure(archivo)
            archivo.seek(0)
            with zipfile.ZipFile(archivo, 'r') as zip_ref:
                kml_content = zip_ref.read(kml_filename)
        else:
            kml_content = archivo.read()

        # 5. Extraer geometrías
        geometries = KMZProcessor.parse_kml_content(kml_content)

        # 6. Guardar en Base de Datos
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
            'mensaje': f'Se importaron correctamente los datos de {proveedor}',
            'proveedor': proveedor,
            'estadisticas': {
                'total_elementos': result['total_count'],
                'guardados': result['saved_count'],
                'errores': len(result['errors'])
            }
        }, status=201)

    except Exception as e:
        import traceback
        traceback.print_exc() # Esto te dirá el error exacto en la consola negra
        return Response({
            'error': 'Error interno al procesar el archivo',
            'detalle': str(e)
        }, status=500)
        
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def listar_archivos_kmz(request):
    """Listar archivos únicos subidos"""
    archivos = CoberturaISP.objects.values('archivo_origen', 'proveedor').annotate(
        total=Count('id')
    ).order_by('archivo_origen')
    return Response(list(archivos))

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def detalle_kmz(request, archivo_kmz):
    """Detalle de un archivo específico"""
    from urllib.parse import unquote
    nombre = unquote(archivo_kmz)
    elementos = CoberturaISP.objects.filter(archivo_origen=nombre)
    return Response({
        "archivo": nombre,
        "total_elementos": elementos.count()
    })

# Asegúrate de que esta función se llame exactamente como en tu urls.py
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_estadisticas(request):
    """Estadísticas para el dashboard"""
    return Response({
        "total_coberturas": CoberturaISP.objects.count(),
        "proveedores": CoberturaISP.objects.values('proveedor').distinct().count()
    })