from collections import OrderedDict

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import CoberturaISP
from .serializers import (
    ConsultaCoberturaSerializer,
    ResultadoCoberturaSerializer,
    ResultadoBusquedaDireccionSerializer,
)


def _agrupar_por_tipo(coberturas):
    nodos = []
    rutas = []
    areas = []

    for cobertura in coberturas:
        geom_type = cobertura.geom.geom_type.upper()

        item = {
            "id": cobertura.id,
            "nombre": cobertura.nombre or "Sin nombre",
            "proveedor": cobertura.proveedor or "Sin proveedor",
            "distancia_metros": round(cobertura.distancia, 2),
            "archivo_origen": cobertura.archivo_origen,
        }

        if "POINT" in geom_type:
            item["tipo_geometria"] = "nodo"
            nodos.append(item)
        elif "LINESTRING" in geom_type:
            item["tipo_geometria"] = "ruta"
            rutas.append(item)
        elif "POLYGON" in geom_type:
            item["tipo_geometria"] = "area"
            areas.append(item)

    return nodos, rutas, areas


def _consultar_por_coordenadas(latitud, longitud, radio_metros):
    coberturas_cercanas = (
        CoberturaISP.objects.extra(
            where=[
                "ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography, %s)"
            ],
            params=[longitud, latitud, radio_metros],
        )
        .extra(
            select={
                "distancia": "ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography)"
            },
            select_params=[longitud, latitud],
        )
        .order_by("distancia")
    )

    isps_disponibles = list(
        coberturas_cercanas.values_list("proveedor", flat=True)
        .distinct()
        .exclude(proveedor__isnull=True)
        .exclude(proveedor="")
    )

    distancia_minima = None
    if coberturas_cercanas.exists():
        distancia_minima = round(coberturas_cercanas.first().distancia, 2)

    nodos, rutas, areas = _agrupar_por_tipo(coberturas_cercanas[:100])

    return {
        "tiene_cobertura": len(isps_disponibles) > 0,
        "isps_disponibles": isps_disponibles,
        "total_isps": len(isps_disponibles),
        "distancia_minima_metros": distancia_minima,
        "nodos_cercanos": nodos,
        "rutas_cercanas": rutas,
        "areas_cercanas": areas,
        "total_nodos": len(nodos),
        "total_rutas": len(rutas),
        "total_areas": len(areas),
        "total_elementos": len(nodos) + len(rutas) + len(areas),
    }


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
