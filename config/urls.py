from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect
from api import views

urlpatterns = [
    path('cobertura/admin/', admin.site.urls),
    path('cobertura/api/', include('api.urls')),

    # Vistas con template
    path('cobertura/login/', views.login_view, name='login'),
    path('cobertura/logout/', views.logout_view, name='logout'),
    path('cobertura/registro/', views.registro_view, name='registro'),

    # Redirect raíz
    path('cobertura/', lambda request: redirect('/cobertura/login/')),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
