from django.urls import path

from . import views

urlpatterns = [
    path("api/consultar-cobertura/", views.consultar_cobertura, name="consultar-cobertura"),
    path("api/geocodificar/", views.geocodificar_direccion, name="geocodificar"),
    path("cobertura/dashboard/", views.dashboard_view, name="dashboard"),
    path("api/buscar-cobertura/", views.buscar_cobertura_por_direccion, name="buscar-cobertura"),
    path("api/filtrar-isp/<str:nombre_isp>/", views.filtrar_por_isp, name="filtrar-isp"),
    path("api/estadisticas/", views.estadisticas_cobertura, name="estadisticas"),
]
