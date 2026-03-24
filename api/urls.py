from django.urls import path, include
from rest_framework.routers import DefaultRouter
#from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views
from . import views_bulk_query

router = DefaultRouter()
router.register(r'usuarios', views.UsuarioViewSet, basename='usuario')
router.register(r'coberturas', views.CoberturaISPViewSet, basename='cobertura')

urlpatterns = [
    # Auth endpoints
    #path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    #path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # API endpoints
    path('', include(router.urls)),
    path('consultar-cobertura/', views.consultar_cobertura, name='consultar_cobertura'),
    path('geocodificar/', views.geocodificar_direccion, name='geocodificar'),
    path('estadisticas/', views.estadisticas_cobertura, name='estadisticas'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('generar-reporte/', views.generar_reporte_pdf, name='generar_reporte'),
    path('detalle-isp/<str:nombre_isp>/', views.detalle_isp, name='detalle-isp'),
    path('detalle-kmz/<path:archivo_kmz>/', views.detalle_kmz, name='detalle-kmz'),
    path('upload-kmz/', views.upload_kmz, name='upload-kmz'),
    path('listar-kmz/', views.listar_archivos_kmz, name='listar-kmz'),
    


    # URLs de Consulta Masiva
    path('bulk-query/upload/', views_bulk_query.upload_bulk_query, name='bulk-query-upload'),
    path('bulk-query/status/<int:job_id>/', views_bulk_query.check_job_status, name='bulk-query-status'),
]
