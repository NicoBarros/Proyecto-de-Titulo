import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
import environ
from django.core.exceptions import ImproperlyConfigured
from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ['localhost', '127.0.0.1']),
    CSRF_TRUSTED_ORIGINS=(list, []),
    WEBSITE_HOSTNAME=(str, ''),
    SECURE_SSL_REDIRECT=(bool, True),
    DOMINIO_INSTITUCIONAL=(str, 'inacapmail.cl'),
    GEMINI_API_KEY=(str, ''),
    GEMINI_MODELO=(str, 'gemini-2.5-flash'),
    GEMINI_MODELO_RESPALDO=(str, 'gemini-2.5-flash-lite'),
    IA_CONSULTAS_POR_HORA=(int, 20),
    TAREAS_TOKEN=(str, ''),
    URL_SITIO=(str, ''),
    EMAIL_HOST=(str, ''),
    EMAIL_PORT=(int, 587),
    EMAIL_HOST_USER=(str, ''),
    EMAIL_HOST_PASSWORD=(str, ''),
    EMAIL_USE_TLS=(bool, True),
    DEFAULT_FROM_EMAIL=(str, 'LEICA Inventario <no-responder@inacapmail.cl>'),
    HORAS_RECORDATORIO=(int, 24),
    POSTGRES_BIN=(str, ''),
    SESION_MINUTOS=(int, 60),
    SECURE_HSTS_SECONDS=(int, 31536000),
    RESPALDOS_DIR=(str, str(BASE_DIR / 'respaldos')),
)
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = env('SECRET_KEY')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env('ALLOWED_HOSTS')
CSRF_TRUSTED_ORIGINS = env('CSRF_TRUSTED_ORIGINS')
INTERNAL_IPS = ['127.0.0.1']

if env('WEBSITE_HOSTNAME'):
    ALLOWED_HOSTS.append(env('WEBSITE_HOSTNAME'))
    CSRF_TRUSTED_ORIGINS.append(f"https://{env('WEBSITE_HOSTNAME')}")

PROXY_CONFIABLE = bool(env('WEBSITE_HOSTNAME'))

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = env('SECURE_SSL_REDIRECT')
    SECURE_HSTS_SECONDS = env('SECURE_HSTS_SECONDS')
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SILENCED_SYSTEM_CHECKS = ['security.W021']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'axes',
    'inventario',
]

MIDDLEWARE = [
    'inventario.middleware.SaludMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.middleware.csp.ContentSecurityPolicyMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'inventario.middleware.NoCacheForAuthenticatedMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',
]

CDN = 'https://cdn.jsdelivr.net'

SECURE_CSP = {
    'default-src': [CSP.SELF],
    'script-src': [CSP.SELF, CDN],
    'style-src': [CSP.SELF, CSP.UNSAFE_INLINE, CDN, 'https://fonts.googleapis.com'],
    'font-src': [CSP.SELF, CDN, 'https://fonts.gstatic.com'],
    'img-src': [CSP.SELF, 'data:'],
    'connect-src': [CSP.SELF],
    'object-src': [CSP.NONE],
    'base-uri': [CSP.SELF],
    'form-action': [CSP.SELF],
    'frame-ancestors': [CSP.NONE],
}

ROOT_URLCONF = 'leica_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

WSGI_APPLICATION = 'leica_project.wsgi.application'

if not env.str('DATABASE_URL', default=''):
    raise ImproperlyConfigured('Define DATABASE_URL con la conexión a PostgreSQL.')

DATABASES = {
    'default': dj_database_url.parse(env('DATABASE_URL'), conn_max_age=600, conn_health_checks=True)
}

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'cache_leica',
    }
}

POSTGRES_BIN = env('POSTGRES_BIN')
RESPALDOS_DIR = env('RESPALDOS_DIR')

AUTH_USER_MODEL = 'inventario.Usuario'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

SESSION_COOKIE_AGE = env('SESION_MINUTOS') * 60
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = [['username', 'ip_address']]
AXES_RESET_ON_SUCCESS = True
AXES_DISABLE_ACCESS_LOG = True
AXES_USERNAME_FORM_FIELD = 'username'
AXES_USERNAME_CALLABLE = 'inventario.seguridad.usuario_intento'
AXES_CLIENT_IP_CALLABLE = 'inventario.seguridad.ip_cliente'
AXES_LOCKOUT_TEMPLATE = 'inventario/bloqueo.html'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-cl'
TIME_ZONE = 'America/Santiago'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

DOMINIO_INSTITUCIONAL = env('DOMINIO_INSTITUCIONAL')
GEMINI_API_KEY = env('GEMINI_API_KEY')
GEMINI_MODELO = env('GEMINI_MODELO')
GEMINI_MODELO_RESPALDO = env('GEMINI_MODELO_RESPALDO')
IA_CONSULTAS_POR_HORA = env('IA_CONSULTAS_POR_HORA')
TAREAS_TOKEN = env('TAREAS_TOKEN')
HORAS_RECORDATORIO = env('HORAS_RECORDATORIO')

if env('URL_SITIO'):
    URL_SITIO = env('URL_SITIO').rstrip('/')
elif env('WEBSITE_HOSTNAME'):
    URL_SITIO = f"https://{env('WEBSITE_HOSTNAME')}"
else:
    URL_SITIO = 'http://127.0.0.1:8000'

EMAIL_HOST = env('EMAIL_HOST')
EMAIL_PORT = env('EMAIL_PORT')
EMAIL_HOST_USER = env('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')
EMAIL_USE_TLS = env('EMAIL_USE_TLS')
EMAIL_TIMEOUT = 15
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL')
EMAIL_BACKEND = (
    'django.core.mail.backends.smtp.EmailBackend' if EMAIL_HOST
    else 'django.core.mail.backends.console.EmailBackend'
)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'WARNING'},
    'loggers': {'inventario.seguridad': {'level': 'INFO'}},
}
