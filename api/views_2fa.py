from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django_otp.plugins.otp_totp.models import TOTPDevice
import qrcode
import io
import base64
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django_ratelimit.decorators import ratelimit

# ===============================================
# VISTAS DE TEMPLATES HTML
# ===============================================

@login_required
def setup_2fa(request):
    """
    Vista HTML para configurar 2FA por primera vez
    GET /cobertura/2fa/setup/
    """
    user = request.user

    # Verificar si ya tiene 2FA configurado
    existing_device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    if existing_device:
        return redirect('/cobertura/2fa/status/')

    # Crear o obtener device no confirmado
    device, created = TOTPDevice.objects.get_or_create(
        user=user,
        name='default',
        confirmed=False
    )

    # Generar URL para QR code
    otpauth_url = device.config_url

    # Generar QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(otpauth_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    # Convertir imagen a base64 para mostrar en HTML
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.getvalue()).decode()

    context = {
        'qr_code': img_base64,
        'secret_key': device.key,
        'device_id': device.id
    }

    return render(request, 'cobertura/setup_2fa.html', context)

@ensure_csrf_cookie
def verify_2fa_login_page(request):
    """
    Vista HTML para verificar código 2FA después del login
    GET /cobertura/2fa/verify-login/
    """
    # Verificar que el usuario esté autenticado
    if not request.user.is_authenticated:
        return redirect('/cobertura/login/')

    # Verificar si ya está verificado
    if request.session.get('otp_verified', False):
        next_url = request.GET.get('next', '/cobertura/mapa/')
        return redirect(next_url)

    return render(request, 'cobertura/verify_2fa.html')


@login_required
def status_2fa_page(request):
    """
    Vista HTML para ver estado de 2FA
    GET /cobertura/2fa/status/
    """
    user = request.user
    device = TOTPDevice.objects.filter(user=user, confirmed=True).first()

    context = {
        'has_2fa': device is not None,
        'device': device
    }

    return render(request, 'cobertura/status_2fa.html', context)


# ===============================================
# API ENDPOINTS (llamados por AJAX desde los templates)
# ===============================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_2fa_setup(request):
    """
    API: Verificar código para confirmar configuración inicial de 2FA
    POST /api/2fa/verify-setup/
    Body: { "code": "123456", "device_id": 1 }
    """
    code = request.data.get('code')
    device_id = request.data.get('device_id')

    if not code:
        return Response({
            'success': False,
            'message': 'Código requerido'
        })

    try:
        device = TOTPDevice.objects.get(id=device_id, user=request.user)

        # Verificar el código
        if device.verify_token(code):
            # Marcar como confirmado
            device.confirmed = True
            device.save()

            return Response({
                'success': True,
                'message': '2FA configurado exitosamente'
            })
        else:
            return Response({
                'success': False,
                'message': 'Código incorrecto. Intenta de nuevo.'
            })
    except TOTPDevice.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Dispositivo no encontrado'
        })


@api_view(['POST'])
@ratelimit(key='ip', rate='10/m', method='POST')
@permission_classes([AllowAny])
def verify_2fa_login(request):
    """
    API: Verificar código 2FA después del login
    POST /api/2fa/verify-login/
    Body: { "code": "123456" }
    """
    # Verificar rate limiting
    was_limited = getattr(request, 'limited', False)
    if was_limited:
        return Response({
            'success': False,
            'message': 'Demasiados intentos de verificación 2FA.'
        }, status=429)

    print(f"[DEBUG verify_2fa_login] User authenticated: {request.user.is_authenticated}")
    print(f"[DEBUG verify_2fa_login] User: {request.user}")
    print(f"[DEBUG verify_2fa_login] Session before: {dict(request.session)}")

    # Verificar que el usuario esté autenticado POR SESIÓN (no JWT)
    if not request.user.is_authenticated:
        return Response({
            'success': False,
            'message': 'Usuario no autenticado'
        }, status=401)

    code = request.data.get('code')

    if not code:
        return Response({
            'success': False,
            'message': 'Código requerido'
        })

    # Obtener device del usuario
    device = TOTPDevice.objects.filter(
        user=request.user,
        confirmed=True
    ).first()

    if not device:
        return Response({
            'success': False,
            'message': 'No tienes 2FA configurado'
        })

    # Verificar el código
    if device.verify_token(code):
        print(f"[DEBUG verify_2fa_login] Token verified successfully")
        # Marcar sesión como verificada
        request.session['otp_verified'] = True
        request.session['pending_2fa'] = False
        request.session.modified = True

        print(f"[DEBUG verify_2fa_login] Session after: {dict(request.session)}")

        # Forzar guardar
        request.session.save()

        print(f"[DEBUG verify_2fa_login] Session saved")
        # Obtener URL de redirección
        next_url = request.GET.get('next', '/cobertura/mapa/')

        return Response({
            'success': True,
            'message': 'Código correcto',
            'redirect_url': next_url
        })
    else:
        return Response({
            'success': False,
            'message': 'Código incorrecto. Intenta de nuevo.'
        })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def disable_2fa(request):
    """
    API: Desactivar 2FA del usuario
    POST /api/2fa/disable/
    Body: { "code": "123456" }
    """
    code = request.data.get('code')

    if not code:
        return Response({
            'success': False,
            'message': 'Código requerido para desactivar 2FA'
        })

    # Obtener device del usuario
    device = TOTPDevice.objects.filter(
        user=request.user,
        confirmed=True
    ).first()

    if not device:
        return Response({
            'success': False,
            'message': 'No tienes 2FA configurado'
        })

    # Verificar código antes de desactivar
    if device.verify_token(code):
        device.delete()

        # Limpiar sesión
        request.session['otp_verified'] = True  # Ya no necesita verificar

        return Response({
            'success': True,
            'message': '2FA desactivado exitosamente'
        })
    else:
        return Response({
            'success': False,
            'message': 'Código incorrecto. No se puede desactivar 2FA.'
        })
