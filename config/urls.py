from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from api.views import login_view, mapa_view, registro_view
from api import views
from api import views_bulk_query

urlpatterns = [
    path('cobertura/admin/', admin.site.urls),
    path('cobertura/api/', include('api.urls')),
    path('cobertura/login/', login_view, name='login'),
    path('cobertura/registro/', registro_view, name='registro'),
    path('cobertura/mapa/', mapa_view, name='mapa'),
    path('cobertura/dashboard/', views.dashboard_view, name='dashboard'),
    path('cobertura/upload/', views.upload_view, name='upload'),
    path('cobertura/', lambda request: redirect('/cobertura/login/')),
    path('cobertura/logout/', views.logout_view, name='logout'),

    # Consulta Masiva (template - requiere autenticación)
    path('cobertura/bulk-query/', views_bulk_query.bulk_query_view, name='bulk-query'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

