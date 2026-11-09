import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse

from .models import Equipo, Usuario

logger = logging.getLogger(__name__)

ASUNTOS = {
    'aprobada': 'Solicitud #{id} aprobada',
    'rechazada': 'Solicitud #{id} rechazada',
    'recordatorio': 'Recordatorio de devolución: solicitud #{id}',
    'atraso': 'Préstamo atrasado: solicitud #{id}',
}


def enviar(tipo, solicitud):
    destinatarios = solicitud.destinatarios()
    if not destinatarios:
        return True
    contexto = {'solicitud': solicitud, 'url': f"{settings.URL_SITIO}{reverse('solicitudes')}"}
    try:
        send_mail(
            ASUNTOS[tipo].format(id=solicitud.id),
            render_to_string(f'inventario/correos/{tipo}.txt', contexto),
            None,
            destinatarios,
        )
    except Exception:
        logger.exception('No se pudo enviar el correo "%s" de la solicitud #%s', tipo, solicitud.id)
        return False
    return True


def notificar(tipo, solicitud):
    transaction.on_commit(lambda: enviar(tipo, solicitud))


def enviar_pendientes_baja(equipos):
    destinatarios = sorted(
        Usuario.objects.filter(rol=Usuario.Rol.CONTROL_CALIDAD, is_active=True).exclude(email='').values_list('email', flat=True)
    )
    if not destinatarios:
        return True
    contexto = {
        'equipos': equipos,
        'años': Equipo.AÑOS_VIDA_UTIL,
        'url': f"{settings.URL_SITIO}{reverse('inventario')}?estado={Equipo.Estado.PENDIENTE_BAJA}",
    }
    try:
        send_mail(
            f'Equipos pendientes de baja ({len(equipos)})',
            render_to_string('inventario/correos/pendiente_baja.txt', contexto),
            None,
            destinatarios,
        )
    except Exception:
        logger.exception('No se pudo enviar el aviso de equipos pendientes de baja')
        return False
    return True


def notificar_pendientes_baja(equipos):
    equipos = list(equipos)
    transaction.on_commit(lambda: enviar_pendientes_baja(equipos))
