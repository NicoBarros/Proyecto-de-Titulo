import ipaddress
import logging

from axes.signals import user_locked_out
from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver
from django.views.defaults import permission_denied

from .models import EventoSeguridad

logger = logging.getLogger('inventario.seguridad')

TIPOS_INFORMATIVOS = (
    EventoSeguridad.Tipo.INICIO_SESION, EventoSeguridad.Tipo.CIERRE_SESION, EventoSeguridad.Tipo.CAMBIO_CUENTA,
)


def _normalizar_ip(valor):
    valor = valor.strip()
    if valor.startswith('['):
        valor = valor[1:].split(']', 1)[0]
    elif valor.count(':') == 1:
        valor = valor.split(':', 1)[0]
    try:
        return str(ipaddress.ip_address(valor))
    except ValueError:
        return None


def ip_cliente(request):
    reenviada = request.META.get('HTTP_X_FORWARDED_FOR', '') if settings.PROXY_CONFIABLE else ''
    if reenviada:
        return _normalizar_ip(reenviada.split(',')[-1])
    return _normalizar_ip(request.META.get('REMOTE_ADDR', ''))


def usuario_intento(request, credenciales):
    datos = credenciales or getattr(request, 'POST', {})
    return (datos.get(settings.AXES_USERNAME_FORM_FIELD) or '').strip().lower()


def registrar_evento(tipo, request=None, usuario=None, identificador='', detalle=''):
    if usuario is not None and not usuario.is_authenticated:
        usuario = None
    evento = EventoSeguridad.objects.create(
        tipo=tipo,
        usuario=usuario,
        identificador=(identificador or getattr(usuario, 'email', '') or '')[:254],
        ip=ip_cliente(request) if request is not None else None,
        ruta=request.path[:255] if request is not None else '',
        agente=request.META.get('HTTP_USER_AGENT', '')[:255] if request is not None else '',
        detalle=detalle[:255],
    )
    nivel = logging.INFO if tipo in TIPOS_INFORMATIVOS else logging.WARNING
    logger.log(nivel, '%s usuario=%s ip=%s ruta=%s %s', tipo, evento.identificador or '-', evento.ip or '-', evento.ruta or '-', evento.detalle)
    return evento


@receiver(user_logged_in)
def _inicio_sesion(sender, request, user, **kwargs):
    registrar_evento(EventoSeguridad.Tipo.INICIO_SESION, request, usuario=user)


@receiver(user_logged_out)
def _cierre_sesion(sender, request, user, **kwargs):
    registrar_evento(EventoSeguridad.Tipo.CIERRE_SESION, request, usuario=user)


@receiver(user_login_failed)
def _intento_fallido(sender, credentials, request=None, **kwargs):
    registrar_evento(
        EventoSeguridad.Tipo.INTENTO_FALLIDO, request,
        identificador=usuario_intento(request, credentials),
    )


@receiver(user_locked_out)
def _bloqueo(sender, request, username, ip_address, **kwargs):
    registrar_evento(
        EventoSeguridad.Tipo.BLOQUEO, request, identificador=(username or '').lower(),
        detalle=f'{settings.AXES_FAILURE_LIMIT} intentos fallidos; bloqueo de {settings.AXES_COOLOFF_TIME}',
    )


def acceso_denegado(request, exception=None):
    registrar_evento(
        EventoSeguridad.Tipo.ACCESO_DENEGADO, request,
        usuario=getattr(request, 'user', None), detalle=str(exception or ''),
    )
    return permission_denied(request, exception)


def registrar_cambio_cuenta(request, objetivo, detalle):
    return registrar_evento(
        EventoSeguridad.Tipo.CAMBIO_CUENTA, request, usuario=request.user, detalle=f'{objetivo.email}: {detalle}',
    )
