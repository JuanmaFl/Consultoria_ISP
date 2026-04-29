from rest_framework.authentication import SessionAuthentication

class CsrfExemptSessionAuthentication(SessionAuthentication):
    """
    SessionAuthentication sin verificación CSRF
    Para usar en APIs que consumen desde el mismo dominio
    """
    def enforce_csrf(self, request):
        return  # No hacer nada = no verificar CSRF
