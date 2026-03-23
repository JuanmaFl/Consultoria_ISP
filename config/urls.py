from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from api import views

urlpatterns = [
    path('cobertura/admin/', admin.site.urls),
    path('cobertura/upload/', views.upload_view, name='upload'),
    path('cobertura/', lambda request: redirect('/cobertura/upload/')),

    # API endpoints
    path('api/upload-kmz/', views.upload_kmz, name='upload-kmz'),
    path('api/listar-kmz/', views.listar_archivos_kmz, name='listar-kmz'),
    path('api/descargar-kmz/<int:archivo_id>/', views.descargar_kmz, name='descargar-kmz'),
    path('api/detalle-kmz/<str:archivo_nombre>/', views.detalle_kmz, name='detalle-kmz'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)