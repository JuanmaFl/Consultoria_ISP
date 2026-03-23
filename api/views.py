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
