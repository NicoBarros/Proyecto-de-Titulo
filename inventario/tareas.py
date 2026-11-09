import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from . import busqueda_semantica, notificaciones, servicios
from .models import Equipo, Solicitud

logger = logging.getLogger(__name__)


def _avisar(solicitudes, tipo, campo):
    enviados = 0
    for solicitud in solicitudes.select_related('solicitante', 'en_representacion_de').prefetch_related(
        'items__equipo', 'items__insumo',
    ):
        if notificaciones.enviar(tipo, solicitud):
            Solicitud.objects.filter(id=solicitud.id).update(**{campo: timezone.now()})
            enviados += 1
    return enviados


def _indexar_busqueda():
    if not settings.BUSQUEDA_SEMANTICA:
        return 0
    try:
        return busqueda_semantica.indexar(Equipo.objects.all())[1]
    except Exception:
        logger.exception('No se pudo actualizar el índice de búsqueda semántica')
        return 0


def ejecutar():
    ahora = timezone.now()
    marcadas = Solicitud.marcar_atrasadas()
    pendientes_baja = servicios.marcar_pendientes_baja()
    recordatorios = _avisar(
        Solicitud.objects.filter(
            estado=Solicitud.EstadoSolicitud.ENTREGADA, recordatorio_enviado__isnull=True,
            horario_fin__gt=ahora, horario_fin__lte=ahora + timedelta(hours=settings.HORAS_RECORDATORIO),
        ),
        'recordatorio', 'recordatorio_enviado',
    )
    atrasos = _avisar(
        Solicitud.objects.filter(estado=Solicitud.EstadoSolicitud.ATRASADA, aviso_atraso_enviado__isnull=True),
        'atraso', 'aviso_atraso_enviado',
    )
    return {
        'atrasadas_marcadas': marcadas, 'recordatorios_enviados': recordatorios, 'avisos_atraso_enviados': atrasos,
        'pendientes_baja_marcados': pendientes_baja,
        'vectores_actualizados': _indexar_busqueda(),
    }
