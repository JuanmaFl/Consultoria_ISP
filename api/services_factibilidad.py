"""
Servicio de análisis de factibilidad de fibra óptica
Combina datos PostGIS (KMZ) + DANE + MinTIC + OpenAI GPT-4
"""

import json
import hashlib
from datetime import timedelta
from django.utils import timezone
from django.db import connection
from django.conf import settings
from .models import CoberturaISP, MunicipioData, AnalisisFactibilidad


def obtener_cobertura_en_zona(tipo_zona, parametros):
    """
    Obtiene estadísticas de cobertura ISP en una zona desde PostGIS
    Retorna dict con ISPs presentes, km estimados, conteos por tipo
    """
    with connection.cursor() as cursor:

        if tipo_zona == 'municipio':
            municipio_nombre = parametros.get('municipio')
            departamento = parametros.get('departamento', '')

            # Buscar municipio en BD
            try:
                mun = MunicipioData.objects.get(
                    nombre__iexact=municipio_nombre,
                    departamento__icontains=departamento
                )
                lat, lng = mun.latitud, mun.longitud
                radio = 15000  # 15km radio para municipio
            except MunicipioData.DoesNotExist:
                return None, None

            cursor.execute("""
                SELECT
                    proveedor,
                    COUNT(*) as total,
                    SUM(CASE WHEN GeometryType(geom) ILIKE '%%LINESTRING%%'
                        THEN ST_Length(geom::geography) / 1000 ELSE 0 END) as km_fibra,
                    COUNT(CASE WHEN GeometryType(geom) ILIKE '%%POINT%%' THEN 1 END) as nodos,
                    COUNT(CASE WHEN GeometryType(geom) ILIKE '%%LINESTRING%%' THEN 1 END) as rutas,
                    COUNT(CASE WHEN GeometryType(geom) ILIKE '%%POLYGON%%' THEN 1 END) as areas
                FROM cobertura_isp
                WHERE ST_DWithin(
                    geom::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                    %s
                )
                AND proveedor IS NOT NULL
                GROUP BY proveedor
                ORDER BY total DESC
            """, [lng, lat, radio])

            municipio_data = mun

        elif tipo_zona == 'departamento':
            departamento = parametros.get('departamento')

            # Obtener municipios del departamento y sus centroides
            municipios = MunicipioData.objects.filter(
                departamento__icontains=departamento
            )

            if not municipios.exists():
                return None, None

            # Usar bbox del departamento (centroide promedio)
            lats = [m.latitud for m in municipios if m.latitud]
            lngs = [m.longitud for m in municipios if m.longitud]
            lat = sum(lats) / len(lats)
            lng = sum(lngs) / len(lngs)
            radio = 200000  # 200km para departamento

            cursor.execute("""
                SELECT
                    proveedor,
                    COUNT(*) as total,
                    SUM(CASE WHEN GeometryType(geom) ILIKE '%%LINESTRING%%'
                        THEN ST_Length(geom::geography) / 1000 ELSE 0 END) as km_fibra,
                    COUNT(CASE WHEN GeometryType(geom) ILIKE '%%POINT%%' THEN 1 END) as nodos,
                    COUNT(CASE WHEN GeometryType(geom) ILIKE '%%LINESTRING%%' THEN 1 END) as rutas,
                    COUNT(CASE WHEN GeometryType(geom) ILIKE '%%POLYGON%%' THEN 1 END) as areas
                FROM cobertura_isp
                WHERE ST_DWithin(
                    geom::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                    %s
                )
                AND proveedor IS NOT NULL
                GROUP BY proveedor
                ORDER BY total DESC
            """, [lng, lat, radio])

            municipio_data = None

        elif tipo_zona == 'radio':
            lat = parametros.get('latitud')
            lng = parametros.get('longitud')
            radio = parametros.get('radio_km', 10) * 1000

            cursor.execute("""
                SELECT
                    proveedor,
                    COUNT(*) as total,
                    SUM(CASE WHEN GeometryType(geom) ILIKE '%%LINESTRING%%'
                        THEN ST_Length(geom::geography) / 1000 ELSE 0 END) as km_fibra,
                    COUNT(CASE WHEN GeometryType(geom) ILIKE '%%POINT%%' THEN 1 END) as nodos,
                    COUNT(CASE WHEN GeometryType(geom) ILIKE '%%LINESTRING%%' THEN 1 END) as rutas,
                    COUNT(CASE WHEN GeometryType(geom) ILIKE '%%POLYGON%%' THEN 1 END) as areas
                FROM cobertura_isp
                WHERE ST_DWithin(
                    geom::geography,
                    ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                    %s
                )
                AND proveedor IS NOT NULL
                GROUP BY proveedor
                ORDER BY total DESC
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
    """Construye el prompt para GPT-4 con contexto real"""

    # Contexto de cobertura existente
    if cobertura['total_isps'] == 0:
        contexto_cobertura = "No hay infraestructura de fibra óptica registrada en esta zona."
    else:
        isps_texto = '\n'.join([
            f"  - {isp['proveedor']}: {isp['km_fibra']:.1f} km de fibra, "
            f"{isp['nodos']} nodos, {isp['rutas']} rutas"
            for isp in cobertura['isps']
        ])
        contexto_cobertura = f"""
Infraestructura de fibra óptica registrada ({cobertura['total_isps']} ISPs):
{isps_texto}
Total: {cobertura['km_fibra_total']:.1f} km de fibra tendida
"""

    # Contexto demográfico
    if municipio_data:
        contexto_demografico = f"""
Datos demográficos (DANE 2018):
- Población total: {municipio_data.poblacion_total:,} habitantes
- Total hogares: {municipio_data.hogares:,}
- NBI (Necesidades Básicas Insatisfechas): {municipio_data.nbi_porcentaje}%
- Área: {municipio_data.area_km2} km²
- Densidad poblacional: {municipio_data.densidad_poblacional} hab/km²
- Proveedores internet según MinTIC: {municipio_data.mintic_proveedores_count}
- Penetración internet estimada: {municipio_data.mintic_penetracion_pct}%
- Tiene fibra según MinTIC: {'Sí' if municipio_data.mintic_tiene_fibra else 'No'}
"""
    else:
        contexto_demografico = "Datos demográficos no disponibles para esta zona específica."

    # Tipo de zona
    if tipo_zona == 'municipio':
        descripcion_zona = f"municipio de {zona_nombre}"
    elif tipo_zona == 'departamento':
        descripcion_zona = f"departamento de {zona_nombre}"
    else:
        radio_km = parametros.get('radio_km', 10)
        descripcion_zona = f"zona de {radio_km} km de radio"

    prompt = f"""Eres un experto en telecomunicaciones e infraestructura de fibra óptica en Colombia.
Analiza la factibilidad de expansión o inversión en fibra óptica (incluyendo fibra oscura) 
para el {descripcion_zona} con los siguientes datos reales:

{contexto_cobertura}

{contexto_demografico}

Genera un análisis ejecutivo estructurado con las siguientes secciones:

1. RESUMEN EJECUTIVO (2-3 oraciones con la conclusión principal)
2. SITUACIÓN ACTUAL (qué infraestructura existe, quiénes operan, nivel de saturación)
3. OPORTUNIDADES (zonas sin cobertura, demanda insatisfecha, potencial de fibra oscura)
4. RIESGOS Y DESAFÍOS (competencia, geografía, regulación, inversión requerida)
5. RECOMENDACIÓN (Alta/Media/Baja factibilidad con justificación)
6. PRÓXIMOS PASOS (3-5 acciones concretas recomendadas)

Al final incluye en formato JSON (entre ```json y ```):
{{
  "score_factibilidad": <número 0-100>,
  "recomendacion": "<alta|media|baja|saturada>",
  "hogares_sin_cobertura_estimados": <número>,
  "inversion_estimada_cop": "<rango en millones COP>"
}}

Sé específico para el contexto colombiano. Menciona regulación CRC, programas de MinTIC 
como Fibra Óptica para la Prosperidad, y considera la topografía de la región."""

    return prompt


def generar_analisis_openai(prompt):
    """Llama a OpenAI GPT-4 y retorna el análisis"""
    from openai import OpenAI

    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    response = client.chat.completions.create(
        model="gpt-4o-mini",  # Más económico que gpt-4, suficiente para este caso
        messages=[
            {
                "role": "system",
                "content": "Eres un consultor experto en infraestructura de telecomunicaciones en Colombia, especializado en fibra óptica y conectividad rural/urbana."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        max_tokens=2000,
        temperature=0.7,
    )

    return response.choices[0].message.content


def extraer_json_del_analisis(texto):
    """Extrae el bloque JSON del texto generado por GPT"""
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
    }


def analizar_factibilidad(tipo_zona, zona_nombre, parametros, usuario):
    """
    Función principal del servicio.
    Retorna análisis cacheado o genera uno nuevo.
    """
    # 1. Verificar cache
    cache_hash = AnalisisFactibilidad.generar_hash(tipo_zona, parametros)
    cache = AnalisisFactibilidad.get_cache_vigente(tipo_zona, parametros)

    if cache:
        return {
            'desde_cache': True,
            'analisis': cache,
        }

    # 2. Obtener cobertura desde PostGIS
    cobertura, municipio_data = obtener_cobertura_en_zona(tipo_zona, parametros)

    if cobertura is None:
        return {'error': f'No se encontraron datos para la zona: {zona_nombre}'}

    # 3. Construir prompt y llamar OpenAI
    prompt = construir_prompt_factibilidad(
        tipo_zona, zona_nombre, parametros, cobertura, municipio_data
    )

    try:
        texto_analisis = generar_analisis_openai(prompt)
    except Exception as e:
        return {'error': f'Error al generar análisis con IA: {str(e)}'}

    # 4. Extraer JSON con métricas
    metricas = extraer_json_del_analisis(texto_analisis)

    # 5. Preparar datos demográficos
    poblacion = municipio_data.poblacion_total if municipio_data else None
    hogares = municipio_data.hogares if municipio_data else None
    penetracion = municipio_data.mintic_penetracion_pct if municipio_data else None

    # 6. Guardar en cache
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
        penetracion_actual_pct=penetracion,
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
