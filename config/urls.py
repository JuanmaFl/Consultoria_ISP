from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from api.views import login_view, mapa_view
from api import views
from api import views_2fa
from api import views_isp_portal
from api import views_bulk_query
from api import views_factibilidad

urlpatterns = [
    path('cobertura/admin/', admin.site.urls),
    path('cobertura/api/', include('api.urls')),
    path('cobertura/login/', login_view, name='login'),
    path('cobertura/mapa/', mapa_view, name='mapa'),
    path('cobertura/dashboard/', views.dashboard_view, name='dashboard'),
    path('cobertura/upload/', views.upload_view, name='upload'),
    path('cobertura/', lambda request: redirect('/cobertura/login/')),
    path('cobertura/logout/', views.logout_view, name='logout'),
    
    # Templates 2FA
    path('cobertura/2fa/setup/', views_2fa.setup_2fa, name='setup-2fa-template'),
    path('cobertura/2fa/verify-login/', views_2fa.verify_2fa_login_page, name='verify-2fa-login-page'),
    path('cobertura/2fa/status/', views_2fa.status_2fa_page, name='status-2fa-page'),
    
    # Portal ISP (templates - sin autenticación)
    path('cobertura/isp-upload/<str:token>/', views_isp_portal.isp_upload_portal, name='isp-upload-portal'),
    
    # Consulta Masiva (template - requiere autenticación)
    path('cobertura/bulk-query/', views_bulk_query.bulk_query_view, name='bulk-query'),

    # Factibilidad - Sprint 3
    path('cobertura/factibilidad/', views_factibilidad.factibilidad_view, name='factibilidad'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
