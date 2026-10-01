"""
Configuracion Django — Sistema de Gestion de Inventario LEICA
INACAP Sede Valdivia

Arquitectura: Django 5.x + PostgreSQL (SQLite en desarrollo local).
Cubre RF-01 a RF-14 segun Formulacion de Proyecto de Titulo.
"""
import os
from pathlib import Path
import environ
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

# --- Variables de entorno ---
env = environ.Env(
    DEBUG=(bool, True),
    SECRET_KEY=(str, 'django-dev-cambia-este-valor-en-produccion'),
    ALLOWED_HOSTS=(list, ['*']),
    DATABASE_URL=(str, ''),
    DOMINIO_INSTITUCIONAL=(str, 'inacapmail.cl'),
    GEMINI_API_KEY=(str, ''),
)
environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

SECRET_KEY = env('SECRET_KEY')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env('ALLOWED_HOSTS')

# --- Aplicaciones ---
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'inventario',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # archivos estaticos en produccion
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
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

# --- Base de datos ---
# En desarrollo usa SQLite; en produccion (Render/Railway) usa la variable
# DATABASE_URL que apunta a PostgreSQL.
if env('DATABASE_URL'):
    DATABASES = {
        'default': dj_database_url.config(default=env('DATABASE_URL'), conn_max_age=600)
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# --- Autenticacion ---
AUTH_USER_MODEL = 'inventario.Usuario'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
]

# --- Internacionalizacion ---
LANGUAGE_CODE = 'es-cl'
TIME_ZONE = 'America/Santiago'
USE_I18N = True
USE_TZ = True

# --- Archivos estaticos ---
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Variables personalizadas del proyecto ---
DOMINIO_INSTITUCIONAL = env('DOMINIO_INSTITUCIONAL')
GEMINI_API_KEY = env('GEMINI_API_KEY')
