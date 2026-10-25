import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse

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
