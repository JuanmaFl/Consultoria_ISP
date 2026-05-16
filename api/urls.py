from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views
from . import views_2fa
from . import views_isp_portal
from . import views_bulk_query
from . import views_factibilidad

router = DefaultRouter()
router.register(r'usuarios', views.UsuarioViewSet, basename='usuario')
router.register(r'coberturas', views.CoberturaISPViewSet, basename='cobertura')

urlpatterns = [
    # Auth endpoints
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # API endpoints
    path('', include(router.urls)),
    path('consultar-cobertura/', views.consultar_cobertura, name='consultar_cobertura'),
    path('geocodificar/', views.geocodificar_direccion, name='geocodificar'),
    path('estadisticas/', views.estadisticas_cobertura, name='estadisticas'),
    path('dashboard/', views.dashboard_estadisticas, name='dashboard'),
    path('generar-reporte/', views.generar_reporte_pdf, name='generar_reporte'),
    path('detalle-isp/<str:nombre_isp>/', views.detalle_isp, name='detalle-isp'),
    path('detalle-kmz/<path:archivo_kmz>/', views.detalle_kmz, name='detalle-kmz'),
    path('upload-kmz/', views.upload_kmz, name='upload-kmz'),
    path('listar-kmz/', views.listar_archivos_kmz, name='listar-kmz'),
    path('listar-proveedores/', views.listar_proveedores, name='listar-proveedores'),
    
    # DELETE KMZ - Sprint 2
    path('delete-kmz/<path:archivo_nombre>/', views.delete_kmz, name='delete-kmz'),
    
    # URLs de 2FA
    path('2fa/setup/', views_2fa.setup_2fa, name='setup-2fa'),
    path('2fa/verify-setup/', views_2fa.verify_2fa_setup, name='verify-2fa-setup'),
    path('2fa/verify-login/', views_2fa.verify_2fa_login, name='verify-2fa-login'),
    path('2fa/status/', views_2fa.status_2fa_page, name='status-2fa'),
    path('2fa/disable/', views_2fa.disable_2fa, name='disable-2fa'),
    
    # URLs de ISP Portal (sin autenticación)
    path('isp-upload/<str:token>/', views_isp_portal.isp_upload_kmz, name='isp-upload-api'),
    
    # URLs de Consulta Masiva
    path('bulk-query/upload/', views_bulk_query.upload_bulk_query, name='bulk-query-upload'),
    path('bulk-query/status/<int:job_id>/', views_bulk_query.check_job_status, name='bulk-query-status'),

    # Factibilidad - Sprint 3
    path('factibilidad/municipios/', views_factibilidad.listar_municipios, name='factibilidad-municipios'),
    path('factibilidad/analizar/', views_factibilidad.generar_analisis, name='factibilidad-analizar'),
    path('factibilidad/historial/', views_factibilidad.historial_analisis, name='factibilidad-historial'),
    path('factibilidad/analisis/<int:analisis_id>/', views_factibilidad.detalle_analisis, name='factibilidad-detalle'),
]
