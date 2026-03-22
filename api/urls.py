from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'usuarios-viewset', views.UsuarioViewSet, basename='usuario')

urlpatterns = [
    # API Router (ViewSet)
    path('', include(router.urls)),

    # API - Registro
    path('registro/', views.api_registro_usuario, name='api-registro'),

    # API - CRUD Usuarios (Admin)
    path('usuarios/', views.listar_usuarios, name='listar-usuarios'),
    path('usuarios/<int:usuario_id>/', views.editar_usuario, name='editar-usuario'),
    path('usuarios/<int:usuario_id>/eliminar/', views.eliminar_usuario, name='eliminar-usuario'),
]
