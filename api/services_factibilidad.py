"""
Servicio de análisis de factibilidad de fibra óptica
Combina datos PostGIS (KMZ) + DANE + MinTIC 2024 + ISPs directorio + OpenAI
"""

import json
import hashlib
from datetime import timedelta
from django.utils import timezone
from django.db import connection
from django.conf import settings
from .models import CoberturaISP, MunicipioData, AnalisisFactibilidad


def obtener_cobertura_en_zona(tipo_zona, parametros):
    with connection.cursor() as cursor:

        if tipo_zona == 'municipio':
            municipio_nombre = parametros.get('municipio')
            departamento = parametros.get('departamento', '')
            try:
                mun = MunicipioData.objects.get(
                    nombre__iexact=municipio_nombre,
                    departamento__icontains=departamento
                )
                lat, lng = mun.latitud, mun.longitud
                radio = 15000
            except MunicipioData.DoesNotExist:
                return None, None

            cursor.execute("""
                SELECT proveedor, COUNT(*) as total,
                    SUM(CASE WHEN GeometryType(geom) ILIKE '%%LINESTRING%%'
                        THEN ST_Length(geom::geography) / 1000 ELSE 0 END) as km_fibra,
                    COUNT(CASE WHEN GeometryType(geom) ILIKE '%%POINT%%' THEN 1 END) as nodos,
                    COUNT(CASE WHEN GeometryType(geom) ILIKE '%%LINESTRING%%' THEN 1 END) as rutas,
                    COUNT(CASE WHEN GeometryType(geom) ILIKE '%%POLYGON%%' THEN 1 END) as areas
                FROM cobertura_isp
                WHERE ST_DWithin(geom::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)
                AND proveedor IS NOT NULL
                GROUP BY proveedor ORDER BY total DESC
            """, [lng, lat, radio])
            municipio_data = mun

        elif tipo_zona == 'departamento':
            departamento = parametros.get('departamento')
            municipios = MunicipioData.objects.filter(departamento__icontains=departamento)
            if not municipios.exists():
                return None, None
            lats = [m.latitud for m in municipios if m.latitud]
            lngs = [m.longitud for m in municipios if m.longitud]
            lat = sum(lats) / len(lats)
            lng = sum(lngs) / len(lngs)
            radio = 200000

            cursor.execute("""
                SELECT proveedor, COUNT(*) as total,
                    SUM(CASE WHEN GeometryType(geom) ILIKE '%%LINESTRING%%'
                        THEN ST_Length(geom::geography) / 1000 ELSE 0 END) as km_fibra,
                    COUNT(CASE WHEN GeometryType(geom) ILIKE '%%POINT%%' THEN 1 END) as nodos,
                    COUNT(CASE WHEN GeometryType(geom) ILIKE '%%LINESTRING%%' THEN 1 END) as rutas,
                    COUNT(CASE WHEN GeometryType(geom) ILIKE '%%POLYGON%%' THEN 1 END) as areas
                FROM cobertura_isp
                WHERE ST_DWithin(geom::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)
                AND proveedor IS NOT NULL
                GROUP BY proveedor ORDER BY total DESC
            """, [lng, lat, radio])
            municipio_data = None

        elif tipo_zona == 'radio':
            lat = parametros.get('latitud')
            lng = parametros.get('longitud')
            radio = parametros.get('radio_km', 10) * 1000

            cursor.execute("""
                SELECT proveedor, COUNT(*) as total,
                    SUM(CASE WHEN GeometryType(geom) ILIKE '%%LINESTRING%%'
                        THEN ST_Length(geom::geography) / 1000 ELSE 0 END) as km_fibra,
                    COUNT(CASE WHEN GeometryType(geom) ILIKE '%%POINT%%' THEN 1 END) as nodos,
                    COUNT(CASE WHEN GeometryType(geom) ILIKE '%%LINESTRING%%' THEN 1 END) as rutas,
                    COUNT(CASE WHEN GeometryType(geom) ILIKE '%%POLYGON%%' THEN 1 END) as areas
                FROM cobertura_isp
                WHERE ST_DWithin(geom::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)
                AND proveedor IS NOT NULL
                GROUP BY proveedor ORDER BY total DESC
            """, [lng, lat, radio])
            municipio_data = None

        rows = cursor.fetchall()

    isps = []
    total_km = 0
    total_registros = 0

    for row in rows:
        proveedor, total, km_fibra, nodos, rutas, areas = row
        isps.append({
            'proveedor': proveedor,
            'total_registros': total,
            'km_fibra': round(float(km_fibra or 0), 2),
            'nodos': nodos,
            'rutas': rutas,
            'areas': areas,
        })
        total_km += float(km_fibra or 0)
        total_registros += total

    resultado = {
        'isps': isps,
        'total_isps': len(isps),
        'total_registros': total_registros,
        'km_fibra_total': round(total_km, 2),
        'nombres_isps': [i['proveedor'] for i in isps],
    }

    return resultado, municipio_data


def construir_prompt_factibilidad(tipo_zona, zona_nombre, parametros, cobertura, municipio_data):

    # Contexto cobertura KMZ
    if cobertura['total_isps'] == 0:
        contexto_cobertura = "No hay infraestructura de fibra óptica registrada en esta zona en el sistema."
    else:
        isps_texto = '\n'.join([
            f"  - {isp['proveedor']}: {isp['km_fibra']:.1f} km fibra, "
            f"{isp['nodos']} nodos, {isp['rutas']} rutas"
            for isp in cobertura['isps']
        ])
        contexto_cobertura = f"""
Infraestructura de fibra óptica registrada en el sistema ({cobertura['total_isps']} operadores):
{isps_texto}
Total: {cobertura['km_fibra_total']:.1f} km de fibra tendida
"""

    # Contexto demográfico + MinTIC real
    if municipio_data:
        # Penetración ajustada (factor 1.8 conexiones por hogar conectado en Colombia)
        penetracion_ajustada = municipio_data.mintic_penetracion_pct
        accesos_reales = getattr(municipio_data, 'mintic_accesos_reales', None)
        proveedores_reales = getattr(municipio_data, 'mintic_proveedores_reales', None)

        if accesos_reales and municipio_data.hogares and municipio_data.hogares > 0:
            penetracion_ajustada = round(
                min(95.0, (accesos_reales / 1.8) / municipio_data.hogares * 100), 1
            )

        # ISPs directorio
        isps_directorio = []
        isps_directorio_raw = getattr(municipio_data, 'isps_directorio', None)
        if isps_directorio_raw:
            try:
                isps_directorio = json.loads(isps_directorio_raw)
            except:
                pass

        # Calcular hogares sin cobertura estimados
        hogares_con_internet = int((accesos_reales or 0) / 1.8) if accesos_reales else 0
        hogares_sin_cobertura = max(0, (municipio_data.hogares or 0) - hogares_con_internet)

        contexto_demografico = f"""
Datos demográficos y conectividad real (DANE 2018 + MinTIC Q4-2024):
- Población total: {municipio_data.poblacion_total:,} habitantes
- Total hogares: {municipio_data.hogares:,}
- Hogares estimados SIN internet: {hogares_sin_cobertura:,} ({round(hogares_sin_cobertura/(municipio_data.hogares or 1)*100,1)}%)
- NBI (Necesidades Básicas Insatisfechas): {municipio_data.nbi_porcentaje}%
- Área: {municipio_data.area_km2} km² | Densidad: {municipio_data.densidad_poblacional} hab/km²
- Accesos fijos internet (MinTIC Q4-2024): {accesos_reales:,} conexiones
- Proveedores activos MinTIC: {proveedores_reales or municipio_data.mintic_proveedores_count}
- Penetración hogares estimada: {penetracion_ajustada}%
- Tiene fibra según MinTIC: {'Sí' if municipio_data.mintic_tiene_fibra else 'No'}
- Operadores en directorio ciudad: {len(isps_directorio)}
"""
        if isps_directorio:
            nombres = [i['empresa'] for i in isps_directorio[:8]]
            contexto_demografico += f"- Operadores registrados: {', '.join(nombres)}\n"

        # Nivel de competencia combinando KMZ + MinTIC
        n_proveedores = proveedores_reales or municipio_data.mintic_proveedores_count or 0
        n_kmz = len(cobertura['isps']) if cobertura else 0
        n_total = max(n_proveedores, n_kmz)

        if n_total == 0:
            nivel_competencia = "ZONA VIRGEN - Sin proveedores registrados"
        elif n_total <= 2:
            nivel_competencia = "COMPETENCIA BAJA - Mercado concentrado"
        elif n_total <= 5:
            nivel_competencia = "COMPETENCIA MEDIA"
        elif n_total <= 15:
            nivel_competencia = "COMPETENCIA ALTA"
        else:
            nivel_competencia = "MERCADO SATURADO - Alta competencia"

        contexto_demografico += f"- Nivel de competencia: {nivel_competencia} ({n_total} operadores totales)\n"
        contexto_demografico += f"- ISPs con infraestructura KMZ en sistema: {n_kmz}\n"
        contexto_demografico += f"- ISPs activos según MinTIC: {n_proveedores}\n"

    # Tipo de zona
    if tipo_zona == 'municipio':
        descripcion_zona = f"municipio de {zona_nombre}"
    elif tipo_zona == 'departamento':
        descripcion_zona = f"departamento de {zona_nombre}"
    else:
        radio_km = parametros.get('radio_km', 10)
        descripcion_zona = f"zona de {radio_km} km de radio"

    prompt = f"""Eres un experto en telecomunicaciones e infraestructura de fibra óptica en Colombia, con amplio conocimiento del mercado ISP colombiano.

Analiza la factibilidad de expansión o inversión en fibra óptica (incluyendo fibra oscura) para el {descripcion_zona}.

DATOS REALES DEL SISTEMA:
{contexto_cobertura}

{contexto_demografico}

Genera un análisis ejecutivo estructurado con estas secciones exactas:

1. RESUMEN EJECUTIVO
(2-3 oraciones con la conclusión principal y el nivel de oportunidad)

2. SITUACIÓN ACTUAL
(infraestructura existente, operadores activos, nivel de penetración actual, saturación del mercado)

3. OPORTUNIDADES DE NEGOCIO
(hogares sin cobertura, segmentos desatendidos, potencial de fibra oscura para wholesale, programas MinTIC aprovechables)

4. RIESGOS Y DESAFÍOS
(competencia existente, inversión requerida, geografía, regulación CRC, tiempo de retorno)

5. RECOMENDACIÓN ESTRATÉGICA
(Alta/Media/Baja/Saturada con justificación específica para esta zona)

6. PRÓXIMOS PASOS
(3-5 acciones concretas y priorizadas)

Al final incluye OBLIGATORIAMENTE este bloque JSON exacto (entre ```json y ```):
{{
  "score_factibilidad": <número 0-100>,
  "recomendacion": "<alta|media|baja|saturada>",
  "hogares_sin_cobertura_estimados": <número>,
  "inversion_estimada_cop": "<rango en millones COP>",
  "tiempo_retorno_anos": <número estimado>
}}

Criterios de score: 0-25=saturado/sin oportunidad, 26-50=baja, 51-75=media, 76-100=alta.
Considera la regulación CRC colombiana, el programa Fibra Óptica para la Prosperidad del MinTIC, y la topografía regional."""

    return prompt


def generar_analisis_openai(prompt):
    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "Eres un consultor senior en infraestructura de telecomunicaciones en Colombia, especializado en fibra óptica, mercado ISP y análisis de inversión."
            },
            {"role": "user", "content": prompt}
        ],
        max_tokens=2500,
        temperature=0.6,
    )
    return response.choices[0].message.content


def extraer_json_del_analisis(texto):
    import re
    match = re.search(r'```json\s*(.*?)\s*```', texto, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return {
        'score_factibilidad': None,
        'recomendacion': None,
        'hogares_sin_cobertura_estimados': None,
        'inversion_estimada_cop': None,
        'tiempo_retorno_anos': None,
    }


def analizar_factibilidad(tipo_zona, zona_nombre, parametros, usuario):
    # 1. Verificar cache
    cache = AnalisisFactibilidad.get_cache_vigente(tipo_zona, parametros)
    if cache:
        return {'desde_cache': True, 'analisis': cache}

    # 2. Cobertura PostGIS
    cobertura, municipio_data = obtener_cobertura_en_zona(tipo_zona, parametros)
    if cobertura is None:
        return {'error': f'No se encontraron datos para la zona: {zona_nombre}'}

    # 3. Prompt + OpenAI
    prompt = construir_prompt_factibilidad(
        tipo_zona, zona_nombre, parametros, cobertura, municipio_data
    )
    try:
        texto_analisis = generar_analisis_openai(prompt)
    except Exception as e:
        return {'error': f'Error al generar análisis con IA: {str(e)}'}

    # 4. Extraer métricas JSON
    metricas = extraer_json_del_analisis(texto_analisis)

    # 5. Penetración ajustada
    poblacion = municipio_data.poblacion_total if municipio_data else None
    hogares = municipio_data.hogares if municipio_data else None
    penetracion_ajustada = None

    if municipio_data:
        accesos_reales = getattr(municipio_data, 'mintic_accesos_reales', None)
        if accesos_reales and hogares and hogares > 0:
            penetracion_ajustada = round(
                min(95.0, (accesos_reales / 1.8) / hogares * 100), 1
            )
        else:
            penetracion_ajustada = municipio_data.mintic_penetracion_pct

    # 6. Guardar cache
    cache_hash = AnalisisFactibilidad.generar_hash(tipo_zona, parametros)
    analisis = AnalisisFactibilidad.objects.create(
        usuario=usuario,
        tipo_zona=tipo_zona,
        zona_nombre=zona_nombre,
        zona_parametros=parametros,
        cache_hash=cache_hash,
        cobertura_isp_count=cobertura['total_registros'],
        isps_presentes=cobertura['nombres_isps'],
        km_fibra_estimados=cobertura['km_fibra_total'],
        poblacion_zona=poblacion,
        hogares_zona=hogares,
        penetracion_actual_pct=penetracion_ajustada,
        analisis_texto=texto_analisis,
        score_factibilidad=metricas.get('score_factibilidad'),
        recomendacion=metricas.get('recomendacion'),
        fecha_expiracion=timezone.now() + timedelta(days=7),
    )

    return {
        'desde_cache': False,
        'analisis': analisis,
        'cobertura_detalle': cobertura,
    }
