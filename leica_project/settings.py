"""
Configuracion Django — Sistema de Gestion de Inventario LEICA
INACAP Sede Valdivia

Arquitectura: Django 5.x + PostgreSQL (SQLite en desarrollo local).
Cubre RF-01 a RF-14 segun Formulacion de Proyecto de Titulo.
"""
import os
from datetime import timedelta
from pathlib import Path
import environ
from django.core.exceptions import ImproperlyConfigured
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ['localhost', '127.0.0.1']),
    CSRF_TRUSTED_ORIGINS=(list, []),
    RENDER_EXTERNAL_HOSTNAME=(str, ''),
    WEBSITE_HOSTNAME=(str, ''),
    SECURE_SSL_REDIRECT=(bool, True),
    DATABASE_URL=(str, ''),
    DOMINIO_INSTITUCIONAL=(str, 'inacapmail.cl'),
    GEMINI_API_KEY=(str, ''),
    GEMINI_MODELO=(str, 'gemini-2.5-flash'),
    GEMINI_MODELO_RESPALDO=(str, 'gemini-2.5-flash-lite'),
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

for dominio_plataforma in (env('WEBSITE_HOSTNAME'), env('RENDER_EXTERNAL_HOSTNAME')):
    if dominio_plataforma:
        ALLOWED_HOSTS.append(dominio_plataforma)
        CSRF_TRUSTED_ORIGINS.append(f'https://{dominio_plataforma}')

PROXY_CONFIABLE = bool(env('WEBSITE_HOSTNAME') or env('RENDER_EXTERNAL_HOSTNAME'))

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

if env('DATABASE_URL'):
    DATABASES = {
        'default': dj_database_url.config(default=env('DATABASE_URL'), conn_max_age=600, conn_health_checks=True)
    }
elif not DEBUG:
    raise ImproperlyConfigured('DATABASE_URL es obligatoria cuando DEBUG=False.')
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
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

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'WARNING'},
    'loggers': {'inventario.seguridad': {'level': 'INFO'}},
}
