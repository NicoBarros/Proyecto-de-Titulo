from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q, Value
from django.db.models.functions import Replace
from django.utils import timezone

from . import notificaciones
from .models import BusquedaIA, EventoSeguridad, Solicitud, SolicitudDerecho

ESTADOS_EN_CURSO = [
    Solicitud.EstadoSolicitud.PENDIENTE, Solicitud.EstadoSolicitud.APROBADA, *Solicitud.ESTADOS_EN_PRESTAMO,
]


def _fecha(valor):
    return timezone.localtime(valor).isoformat() if valor else None


def _solicitudes(usuario):
    return (
        Solicitud.objects.filter(Q(solicitante=usuario) | Q(en_representacion_de=usuario))
        .select_related('solicitante', 'en_representacion_de')
        .prefetch_related('items__equipo', 'items__insumo', 'movimientos')
        .order_by('-created_at')
    )


def _item(item):
    articulo = item.equipo or item.insumo
    return {
        'tipo': 'equipo' if item.equipo_id else 'insumo',
        'nombre': articulo.nombre,
        'codigo_inventario': item.equipo.codigo_inventario if item.equipo_id else None,
        'cantidad': item.cantidad,
        'estado_devolucion': item.estado_devolucion or None,
    }


def _solicitud(solicitud, usuario):
    return {
        'id': solicitud.id,
        'participacion': 'solicitante' if solicitud.solicitante_id == usuario.id else 'en representación',
        'estado': solicitud.get_estado_display(),
        'creada': _fecha(solicitud.created_at),
        'horario_inicio': _fecha(solicitud.horario_inicio),
        'horario_fin': _fecha(solicitud.horario_fin),
        'lugar_uso': solicitud.get_lugar_uso_display(),
        'justificacion': solicitud.justificacion or '',
        'motivo_rechazo': solicitud.motivo_rechazo,
        'items': [_item(i) for i in solicitud.items.all()],
        'movimientos': [
            {'tipo': m.get_tipo_display(), 'fecha': _fecha(m.fecha), 'observacion': m.observacion or ''}
            for m in solicitud.movimientos.all()
        ],
    }


def datos_personales(usuario):
    return {
        'generado': _fecha(timezone.now()),
        'responsable': 'Laboratorio LEICA · INACAP Sede Valdivia',
        'perfil': {
            'nombre': usuario.first_name,
            'apellido': usuario.last_name,
            'correo': usuario.email,
            'rol': usuario.get_rol_display(),
            'seccion': usuario.seccion or None,
            'cuenta_activa': usuario.is_active,
            'registrado': _fecha(usuario.date_joined),
            'ultimo_acceso': _fecha(usuario.last_login),
            'bloqueado_hasta': _fecha(usuario.bloqueado_hasta),
        },
        'solicitudes': [_solicitud(s, usuario) for s in _solicitudes(usuario)],
        'bloqueos': [
            {'inicio': _fecha(b.fecha_inicio), 'fin': _fecha(b.fecha_fin), 'motivo': b.motivo or '',
             'seccion': b.seccion or None}
            for b in usuario.bloqueos.order_by('-fecha_inicio')
        ],
        'busquedas': [
            {'fecha': _fecha(b.fecha), 'consulta': b.consulta, 'resultados': b.resultados,
             'respuesta': b.respuesta if b.generacion == BusquedaIA.Generacion.GENERADA else '',
             'calificacion': {True: 'útil', False: 'no útil'}.get(b.util)}
            for b in usuario.busquedas.order_by('-fecha')
        ],
        'eventos_seguridad': [
            {'fecha': _fecha(e.fecha), 'tipo': e.get_tipo_display(), 'ip': e.ip, 'navegador': e.agente,
             'detalle': e.detalle}
            for e in EventoSeguridad.objects.filter(Q(usuario=usuario) | Q(identificador=usuario.email)).order_by('-fecha')
        ],
        'solicitudes_derechos': [
            {'fecha': _fecha(d.creada), 'tipo': d.get_tipo_display(), 'detalle': d.detalle,
             'estado': d.get_estado_display(), 'respuesta': d.respuesta, 'resuelta': _fecha(d.resuelta_en)}
            for d in usuario.solicitudes_derechos.all()
        ],
    }


def resumen(usuario):
    return {
        'solicitudes': _solicitudes(usuario).count(),
        'bloqueos': usuario.bloqueos.count(),
        'busquedas': usuario.busquedas.count(),
        'eventos': EventoSeguridad.objects.filter(Q(usuario=usuario) | Q(identificador=usuario.email)).count(),
    }


def crear_solicitud_derecho(usuario, tipo, detalle):
    if tipo not in SolicitudDerecho.Tipo.values:
        raise ValueError('Selecciona un derecho válido.')
    detalle = (detalle or '').strip()
    if not detalle:
        raise ValueError('Describe tu solicitud.')
    if usuario.solicitudes_derechos.filter(tipo=tipo, estado=SolicitudDerecho.Estado.PENDIENTE).exists():
        raise ValueError('Ya tienes una solicitud pendiente de ese tipo.')
    solicitud = SolicitudDerecho.objects.create(
        usuario=usuario, identificador=usuario.email, tipo=tipo, detalle=detalle[:2000],
    )
    transaction.on_commit(lambda: notificaciones.enviar_solicitud_derecho(solicitud))
    return solicitud


def anonimizar_usuario(usuario):
    if Solicitud.objects.filter(
        Q(solicitante=usuario) | Q(en_representacion_de=usuario), estado__in=ESTADOS_EN_CURSO,
    ).exists():
        raise ValueError('La cuenta tiene solicitudes o préstamos en curso; deben cerrarse antes de suprimir sus datos.')
    correo = usuario.email
    alias = f'anonimo-{usuario.id}'
    usuario.username = alias
    usuario.email = f'{alias}@anonimo.invalid'
    usuario.first_name = 'Titular'
    usuario.last_name = 'anonimizado'
    usuario.seccion = None
    usuario.bloqueado_hasta = None
    usuario.is_active = False
    usuario.set_unusable_password()
    usuario.save()
    usuario.busquedas.update(usuario=None)
    EventoSeguridad.objects.filter(Q(usuario=usuario) | Q(identificador=correo)).update(
        usuario=None, identificador='', ip=None, agente='',
    )
    EventoSeguridad.objects.filter(detalle__contains=correo).update(
        detalle=Replace('detalle', Value(correo), Value(alias)),
    )
    usuario.solicitudes_derechos.update(identificador=alias)
    return alias


@transaction.atomic
def resolver_solicitud_derecho(solicitud_id, administrador, aceptar, respuesta):
    solicitud = SolicitudDerecho.objects.select_for_update(of=('self',)).select_related('usuario').filter(
        id=solicitud_id if str(solicitud_id or '').isdigit() else None,
    ).first()
    if solicitud is None:
        raise ValueError('La solicitud no existe.')
    if solicitud.estado != SolicitudDerecho.Estado.PENDIENTE:
        raise ValueError('La solicitud ya fue resuelta.')
    respuesta = (respuesta or '').strip()
    if not respuesta:
        raise ValueError('Escribe la respuesta para el titular.')
    titular = solicitud.usuario
    correo = titular.email if titular else ''
    if aceptar and titular is not None:
        if solicitud.tipo == SolicitudDerecho.Tipo.SUPRESION:
            solicitud.identificador = anonimizar_usuario(titular)
        elif solicitud.tipo == SolicitudDerecho.Tipo.BLOQUEO:
            titular.is_active = False
            titular.save(update_fields=['is_active'])
    solicitud.estado = SolicitudDerecho.Estado.ACEPTADA if aceptar else SolicitudDerecho.Estado.RECHAZADA
    solicitud.respuesta = respuesta[:2000]
    solicitud.resuelta_en = timezone.now()
    solicitud.resuelta_por = administrador
    solicitud.save()
    if correo:
        transaction.on_commit(lambda: notificaciones.enviar_respuesta_derecho(solicitud, correo))
    return solicitud


def depurar_datos_antiguos():
    ahora = timezone.now()
    busquedas = BusquedaIA.objects.filter(
        usuario__isnull=False, fecha__lt=ahora - timedelta(days=settings.RETENCION_BUSQUEDAS_DIAS),
    ).update(usuario=None)
    eventos, _ = EventoSeguridad.objects.filter(
        fecha__lt=ahora - timedelta(days=settings.RETENCION_EVENTOS_DIAS),
    ).delete()
    return {'busquedas_anonimizadas': busquedas, 'eventos_eliminados': eventos}
