from django.shortcuts import redirect
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice


class Enforce2FAMiddleware:
    """
    Middleware para forzar verificación 2FA si el usuario lo tiene configurado
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        
        # URLs que no requieren 2FA
        self.exempt_urls = [
            '/cobertura/login/',
            '/cobertura/2fa/',           # Toda la sección de 2FA (templates)
            '/cobertura/api/2fa/',       # APIs de 2FA
            '/cobertura/api/token/',     # JWT tokens
            '/cobertura/admin/',
            '/static/',
            '/media/',
        ]
    def __call__(self, request):
        # Si el usuario está autenticado
        if request.user.is_authenticated:
            # Verificar si tiene 2FA configurado
            has_2fa = TOTPDevice.objects.filter(
                user=request.user, 
                confirmed=True
            ).exists()
            
            # Si tiene 2FA y no está verificado en esta sesión
            if has_2fa and not request.session.get('otp_verified', False):
                # Verificar si la URL actual está exenta
                current_path = request.path
                is_exempt = any(current_path.startswith(url) for url in self.exempt_urls)
                
                if not is_exempt:
                    # Redirigir a verificación 2FA
                    return redirect(f'/cobertura/2fa/verify-login/?next={current_path}')

        response = self.get_response(request)
        return response
