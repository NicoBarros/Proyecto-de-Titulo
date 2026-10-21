import logging

from django.db import connection
from django.http import JsonResponse
from django.utils.cache import add_never_cache_headers

logger = logging.getLogger(__name__)


class SaludMiddleware:
    RUTA = '/salud/'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path != self.RUTA:
            return self.get_response(request)
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
            respuesta = JsonResponse({'estado': 'ok', 'base_de_datos': 'ok'})
        except Exception:
            logger.exception('Verificación de salud fallida: sin conexión a la base de datos')
            respuesta = JsonResponse({'estado': 'error', 'base_de_datos': 'sin conexión'}, status=503)
        add_never_cache_headers(respuesta)
        return respuesta


class NoCacheForAuthenticatedMiddleware:
    """
    Evita que el navegador almacene en caché páginas autenticadas.
    Al cerrar sesión, si el usuario presiona el botón 'Atrás' en el navegador,
    este no mostrará la página desde la memoria caché y obligará a revalidar
    con el servidor (el cual redirigirá a la vista de login).
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if hasattr(request, 'user') and request.user.is_authenticated:
            add_never_cache_headers(response)
            response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        return response
