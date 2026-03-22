from rest_framework import viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny, IsAdminUser
from django.contrib.auth import authenticate, login as django_login, logout as django_logout
from django.contrib.auth import get_user_model
from django.shortcuts import render, redirect
from .serializers import UsuarioSerializer, RegistroUsuarioSerializer

Usuario = get_user_model()


# =============================================================================
# VIEWSET DE USUARIOS (lectura desde API)
# =============================================================================

class UsuarioViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet para usuarios (solo lectura desde API)"""
    queryset = Usuario.objects.all()
    serializer_class = UsuarioSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def me(self, request):
        """Obtener información del usuario actual"""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)


# =============================================================================
# VISTAS DE LOGIN / LOGOUT (sesión Django)
# =============================================================================

def login_view(request):
    """Vista de login con sesión Django"""
    if request.user.is_authenticated:
        return redirect('/cobertura/login/')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            django_login(request, user)
            next_url = request.GET.get('next', '/cobertura/login/')
            return redirect(next_url)
        else:
            return render(request, 'cobertura/login.html', {
                'error': 'Usuario o contraseña incorrectos'
            })

    return render(request, 'cobertura/login.html')


def logout_view(request):
    """Vista de logout - Cerrar sesión"""
    django_logout(request)
    return redirect('/cobertura/login/')


# =============================================================================
# VISTA DE REGISTRO (template)
# =============================================================================

def registro_view(request):
    """Vista de registro de nuevos usuarios"""
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        password2 = request.POST.get('password2')

        # Validaciones
        errors = []

        if not username or not email or not password:
            errors.append('Todos los campos son obligatorios.')

        if password != password2:
            errors.append('Las contraseñas no coinciden.')

        if len(password) < 8:
            errors.append('La contraseña debe tener al menos 8 caracteres.')

        if Usuario.objects.filter(username=username).exists():
            errors.append('Este nombre de usuario ya existe.')

        if Usuario.objects.filter(email=email).exists():
            errors.append('Este email ya está registrado.')

        if errors:
            return render(request, 'cobertura/registro.html', {
                'errors': errors,
                'username': username,
                'email': email,
            })

        # Crear usuario
        user = Usuario.objects.create_user(
            username=username,
            email=email,
            password=password,
        )

        return redirect('/cobertura/login/')

    return render(request, 'cobertura/registro.html')


# =============================================================================
# API ENDPOINTS - REGISTRO
# =============================================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def api_registro_usuario(request):
    """Endpoint para registrar nuevo usuario"""
    serializer = RegistroUsuarioSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user = Usuario.objects.create_user(
        username=serializer.validated_data['username'],
        email=serializer.validated_data['email'],
        password=serializer.validated_data['password'],
    )

    return Response({
        'mensaje': 'Usuario registrado exitosamente.',
        'usuario': UsuarioSerializer(user).data,
    }, status=status.HTTP_201_CREATED)


# =============================================================================
# API ENDPOINTS - CRUD DE USUARIOS (Solo Admin)
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def listar_usuarios(request):
    """Listar todos los usuarios (solo admin)"""
    if not request.user.is_staff:
        return Response(
            {'error': 'No tienes permisos para realizar esta acción.'},
            status=status.HTTP_403_FORBIDDEN
        )

    usuarios = Usuario.objects.all()
    serializer = UsuarioSerializer(usuarios, many=True)
    return Response(serializer.data)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def editar_usuario(request, usuario_id):
    """Editar usuario específico (solo admin)"""
    if not request.user.is_staff:
        return Response(
            {'error': 'No tienes permisos para realizar esta acción.'},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        usuario = Usuario.objects.get(id=usuario_id)
    except Usuario.DoesNotExist:
        return Response(
            {'error': 'Usuario no encontrado.'},
            status=status.HTTP_404_NOT_FOUND
        )

    serializer = UsuarioSerializer(usuario, data=request.data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    serializer.save()
    return Response({
        'mensaje': 'Usuario actualizado exitosamente.',
        'usuario': serializer.data,
    })


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def eliminar_usuario(request, usuario_id):
    """Eliminar usuario (solo admin)"""
    if not request.user.is_staff:
        return Response(
            {'error': 'No tienes permisos para realizar esta acción.'},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        usuario = Usuario.objects.get(id=usuario_id)
    except Usuario.DoesNotExist:
        return Response(
            {'error': 'Usuario no encontrado.'},
            status=status.HTTP_404_NOT_FOUND
        )

    if usuario.is_superuser:
        return Response(
            {'error': 'No se puede eliminar un superusuario.'},
            status=status.HTTP_403_FORBIDDEN
        )

    usuario.delete()
    return Response({
        'mensaje': 'Usuario eliminado exitosamente.',
    }, status=status.HTTP_200_OK)
