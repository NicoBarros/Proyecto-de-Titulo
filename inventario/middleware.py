from django.utils.cache import add_never_cache_headers

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
