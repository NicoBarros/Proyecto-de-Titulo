"""URL principal del proyecto LEICA."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('inventario.urls')),
]

handler403 = 'inventario.seguridad.acceso_denegado'
