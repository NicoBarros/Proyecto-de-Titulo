import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from . import busqueda_semantica, evaluacion_busqueda, notificaciones, privacidad, respaldos, servicios
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


def _escalar_revisiones():
    limite = timezone.now() - timedelta(hours=settings.SLA_REVISION_HORAS)
    vencidas = list(
        Solicitud.objects.filter(
            estado=Solicitud.EstadoSolicitud.PENDIENTE, created_at__lt=limite, aviso_revision_enviado__isnull=True,
        ).select_related('solicitante', 'en_representacion_de').order_by('created_at')
    )
    if not vencidas or not notificaciones.enviar_revisiones_vencidas(vencidas):
        return 0
    Solicitud.objects.filter(id__in=[s.id for s in vencidas]).update(aviso_revision_enviado=timezone.now())
    return len(vencidas)


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
        'revisiones_escaladas': _escalar_revisiones(),
        'datos_depurados': privacidad.depurar_datos_antiguos(),
        'vectores_actualizados': _indexar_busqueda(),
        'respaldo': respaldos.respaldo_automatico(),
        'evaluacion_busqueda': evaluacion_busqueda.evaluacion_mensual(),
    }
