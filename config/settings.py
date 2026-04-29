from pathlib import Path
from decouple import config
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

# ==============================================================================
# CORE SETTINGS
# ==============================================================================

SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='').split(',')

APPEND_SLASH = True

# ==============================================================================
# INSTALLED APPS
# ==============================================================================

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.gis',
    
    # Django OTP (2FA)
    'django_otp',
    'django_otp.plugins.otp_totp',
    'django_otp.plugins.otp_static',
    
    # Third party
    'rest_framework',
    'corsheaders',

    # Local
    'api',
]

# ==============================================================================
# MIDDLEWARE
# ==============================================================================

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_otp.middleware.OTPMiddleware',
    'api.middleware.Enforce2FAMiddleware',
]

# ==============================================================================
# TEMPLATES
# ==============================================================================

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ==============================================================================
# DATABASE
# ==============================================================================

DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': config('DATABASE_NAME'),
        'USER': config('DATABASE_USER'),
        'PASSWORD': config('DATABASE_PASSWORD'),
        'HOST': config('DATABASE_HOST'),
        'PORT': config('DATABASE_PORT'),
        'CONN_MAX_AGE': 600,
    }
}

# ==============================================================================
# AUTH & PASSWORD VALIDATION
# ==============================================================================

AUTH_USER_MODEL = 'api.Usuario'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = '/cobertura/login/'
LOGIN_REDIRECT_URL = '/cobertura/mapa/'
LOGOUT_REDIRECT_URL = '/cobertura/login/'

# ==============================================================================
# INTERNATIONALIZATION
# ==============================================================================

LANGUAGE_CODE = 'es-co'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_TZ = True

# ==============================================================================
# STATIC & MEDIA FILES
# ==============================================================================

STATIC_URL = '/cobertura/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

if DEBUG:
    import os
    STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

MEDIA_URL = '/cobertura/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ==============================================================================
# SESSION SETTINGS
# ==============================================================================

SESSION_COOKIE_SECURE = False  # False para HTTP, True solo si usas HTTPS
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 3600  # 1 hora
SESSION_SAVE_EVERY_REQUEST = True  # Importante para 2FA
SESSION_COOKIE_NAME = 'cobertura_sessionid'
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
# ==============================================================================
# CSRF SETTINGS
# ==============================================================================

CSRF_COOKIE_SECURE = False  # False para HTTP, True solo si usas HTTPS
CSRF_COOKIE_HTTPONLY = False  # False para permitir acceso desde JavaScript
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_TRUSTED_ORIGINS = [
    'http://86.48.21.76',
    'http://localhost:8000',
]

# ==============================================================================
# SECURITY SETTINGS
# ==============================================================================

SECURE_SSL_REDIRECT = False  # Lo manejamos en nginx
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
# ==============================================================================
# REST FRAMEWORK
# ==============================================================================

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'api.authentication.CsrfExemptSessionAuthentication',  # Sesión sin CSRF
        'rest_framework_simplejwt.authentication.JWTAuthentication',  # JWT como fallback
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
}

# ==============================================================================
# JWT SETTINGS
# ==============================================================================

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ==============================================================================
# CORS SETTINGS
# ==============================================================================

CORS_ALLOWED_ORIGINS = [
    "http://86.48.21.76",
    "http://localhost:8000",
]

CORS_ALLOW_CREDENTIALS = True

# ==============================================================================
# GOOGLE MAPS
# ==============================================================================

GOOGLE_MAPS_API_KEY = config('GOOGLE_MAPS_API_KEY', default='')

# ==============================================================================
# LOGGING
# ==============================================================================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'WARNING',
            'class': 'logging.FileHandler',
            'filename': '/opt/cobertura_isp/logs/security.log',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django.security': {
            'handlers': ['file'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}
