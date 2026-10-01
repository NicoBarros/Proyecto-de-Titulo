"""
Decoradores y utilidades de autenticacion para vistas Django.
"""
from django.core.exceptions import PermissionDenied
from functools import wraps

def role_required(*roles):
    """
    Decorador para requerir que el usuario logueado tenga alguno de los roles
    especificados. Reemplaza al middleware de Express 'requireRole'.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                # Si no esta autenticado, dejar que lo maneje @login_required
                return view_func(request, *args, **kwargs)
            
            if request.user.rol not in roles:
                raise PermissionDenied(f"Rol {request.user.rol} no autorizado. Se requiere: {', '.join(roles)}")
                
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
