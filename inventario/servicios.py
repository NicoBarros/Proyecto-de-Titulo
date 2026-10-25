from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from . import auditoria, notificaciones
from .models import (
    Bloqueo,
    Equipo,
    HistorialEquipo,
    Insumo,
    Mantenimiento,
    Movimiento,
    Solicitud,
    SolicitudItem,
    Usuario,
)

DIAS_SANCION = 7
UMBRAL_BAJA = Decimal('0.70')

TRANSICIONES_SOLICITUD = {
    'aprobar': [Solicitud.EstadoSolicitud.PENDIENTE],
    'rechazar': [Solicitud.EstadoSolicitud.PENDIENTE, Solicitud.EstadoSolicitud.APROBADA],
    'entregar': [Solicitud.EstadoSolicitud.APROBADA],
    'devolver': Solicitud.ESTADOS_EN_PRESTAMO,
    'cancelar': [Solicitud.EstadoSolicitud.PENDIENTE, Solicitud.EstadoSolicitud.APROBADA],
}

PARTICIPIOS_ACCION = {
    'aprobar': 'aprobada',
    'rechazar': 'rechazada',
    'entregar': 'entregada',
    'devolver': 'devuelta',
    'cancelar': 'cancelada',
}

ESTADOS_DEVOLUCION = SolicitudItem.EstadoDevolucion.values

ACCIONES_MANTENIMIENTO = {
    'completar_reparacion': (Mantenimiento.Decision.COMPLETADO, Equipo.Estado.DISPONIBLE, 'reparación completada'),
    'completado': (Mantenimiento.Decision.COMPLETADO, Equipo.Estado.DISPONIBLE, 'reparación completada'),
    'dar_baja': (Mantenimiento.Decision.DAR_BAJA, Equipo.Estado.FUERA_SERVICIO, 'dado de baja'),
    'reparar': (Mantenimiento.Decision.REPARAR, Equipo.Estado.EN_MANTENIMIENTO, 'en reparación'),
}

ESTADOS_DIAGNOSTICABLES = [Equipo.Estado.DISPONIBLE, Equipo.Estado.EN_MANTENIMIENTO]


def cambiar_estado_equipo(equipo, usuario, estado, detalle):
    if equipo.estado == estado:
        return
    antes = auditoria.foto(equipo)
    equipo.estado = estado
    equipo.version += 1
    equipo.save(update_fields=['estado', 'version', 'updated_at'])
    auditoria.registrar(equipo, usuario, HistorialEquipo.Accion.ESTADO, antes, detalle)


def _fecha_texto(fecha):
    return timezone.localtime(fecha).strftime('%d-%m-%Y %H:%M')


def _nombre(usuario):
    return usuario.get_full_name() or usuario.email


def _validar_puede_solicitar(usuario, representado):
    if usuario.esta_bloqueado():
        raise ValueError(f'Tu cuenta está bloqueada para solicitar préstamos hasta el {_fecha_texto(usuario.bloqueado_hasta)}.')
    if representado and representado.esta_bloqueado():
        raise ValueError(f'{_nombre(representado)} está bloqueado para préstamos hasta el {_fecha_texto(representado.bloqueado_hasta)}.')
    if (representado or usuario).tiene_atrasos():
        if representado:
            raise ValueError(f'{_nombre(representado)} tiene préstamos atrasados sin devolver.')
        raise ValueError('Tienes préstamos atrasados sin devolver. Devuélvelos antes de crear una nueva solicitud.')


def _representado(usuario, representado_id):
    representado_id = (representado_id or '').strip()
    if not representado_id:
        return None
    if usuario.rol not in Usuario.ROLES_REPRESENTANTES:
        raise ValueError('Tu rol no permite solicitar en representación de un estudiante.')
    representado = Usuario.objects.filter(
        id=representado_id if representado_id.isdigit() else None,
        rol=Usuario.Rol.ESTUDIANTE, is_active=True,
    ).first()
    if representado is None:
        raise ValueError('El estudiante seleccionado no es válido.')
    return representado


def _items_pedidos(items, cantidades):
    equipos_ids, insumos_cant = [], {}
    for i, valor in enumerate(items):
        tipo, _, item_id = valor.partition(':')
        try:
            item_id = int(item_id)
            cantidad = int(cantidades[i]) if i < len(cantidades) else 1
        except ValueError:
            raise ValueError('Ítem o cantidad no válidos.')
        if cantidad < 1:
            raise ValueError('La cantidad debe ser al menos 1.')
        if tipo == 'equipo':
            if item_id in equipos_ids:
                raise ValueError('No puedes repetir el mismo equipo en una solicitud.')
            equipos_ids.append(item_id)
        elif tipo == 'insumo':
            insumos_cant[item_id] = insumos_cant.get(item_id, 0) + cantidad
        else:
            raise ValueError('Ítem no válido.')
    if not equipos_ids and not insumos_cant:
        raise ValueError('La solicitud debe tener al menos un ítem.')
    return equipos_ids, insumos_cant


@transaction.atomic
def crear_solicitud(usuario, items, cantidades, inicio, fin, lugar_uso, justificacion, representado_id=None):
    representado = _representado(usuario, representado_id)
    _validar_puede_solicitar(usuario, representado)
    if inicio is None or fin is None:
        raise ValueError('Debes indicar un horario de inicio y de fin válidos.')
    if fin <= inicio:
        raise ValueError('El horario de fin debe ser posterior al de inicio.')
    lugar_uso = lugar_uso or Solicitud.LugarUso.DENTRO_SEDE
    if lugar_uso not in Solicitud.LugarUso.values:
        raise ValueError('Lugar de uso no válido.')
    equipos_ids, insumos_cant = _items_pedidos(items, cantidades)

    solicitud = Solicitud.objects.create(
        solicitante=usuario, en_representacion_de=representado, lugar_uso=lugar_uso,
        justificacion=justificacion, horario_inicio=inicio, horario_fin=fin,
    )
    equipos = Equipo.objects.in_bulk(equipos_ids)
    for item_id in equipos_ids:
        equipo = equipos.get(item_id)
        if equipo is None:
            raise ValueError('Uno de los equipos seleccionados no existe.')
        if equipo.estado != Equipo.Estado.DISPONIBLE:
            raise ValueError(f'El equipo {equipo.nombre} no se encuentra disponible actualmente.')
        SolicitudItem.objects.create(solicitud=solicitud, equipo=equipo, cantidad=1)
    insumos = Insumo.objects.in_bulk(insumos_cant)
    for item_id, cantidad in insumos_cant.items():
        insumo = insumos.get(item_id)
        if insumo is None:
            raise ValueError('Uno de los insumos seleccionados no existe.')
        if insumo.cantidad_disponible < cantidad:
            raise ValueError(f'No hay stock suficiente para {insumo.nombre}. Disponible: {insumo.cantidad_disponible}.')
        SolicitudItem.objects.create(solicitud=solicitud, insumo=insumo, cantidad=cantidad)
    return solicitud


def _aprobar(solicitud, equipos, usuario):
    for equipo in equipos:
        if equipo.estado in (Equipo.Estado.EN_MANTENIMIENTO, Equipo.Estado.FUERA_SERVICIO):
            raise ValueError(f'El equipo {equipo.nombre} está {equipo.get_estado_display().lower()}.')
        choque = SolicitudItem.objects.filter(
            equipo=equipo,
            solicitud__estado__in=[Solicitud.EstadoSolicitud.APROBADA, *Solicitud.ESTADOS_EN_PRESTAMO],
            solicitud__horario_inicio__lt=solicitud.horario_fin,
            solicitud__horario_fin__gt=solicitud.horario_inicio,
        ).exclude(solicitud=solicitud).exists()
        if choque:
            raise ValueError(f'El equipo {equipo} ya esta reservado en ese horario.')
    solicitud.estado = Solicitud.EstadoSolicitud.APROBADA
    solicitud.aprobado_por = usuario
    solicitud.fecha_aprobacion = timezone.now()
    solicitud.save()
    notificaciones.notificar('aprobada', solicitud)


def _entregar(solicitud, equipos, items, usuario):
    for equipo in equipos:
        if equipo.estado != Equipo.Estado.DISPONIBLE:
            raise ValueError(f'El equipo {equipo.nombre} no está disponible para entregar.')
        cambiar_estado_equipo(equipo, usuario, Equipo.Estado.PRESTADO, f'Entrega de la solicitud #{solicitud.id}')
    for item in items:
        if item.insumo_id:
            actualizados = Insumo.objects.filter(
                id=item.insumo_id, cantidad_disponible__gte=item.cantidad,
            ).update(cantidad_disponible=F('cantidad_disponible') - item.cantidad, version=F('version') + 1)
            if not actualizados:
                raise ValueError(f'Stock insuficiente para {item.insumo.nombre}.')
    solicitud.estado = Solicitud.EstadoSolicitud.ENTREGADA
    solicitud.save()
    Movimiento.objects.create(solicitud=solicitud, tipo=Movimiento.TipoMovimiento.ENTREGA, responsable=usuario)


def sancionar(usuario, solicitud):
    hasta = timezone.now() + timedelta(days=DIAS_SANCION)
    if not usuario.bloqueado_hasta or usuario.bloqueado_hasta < hasta:
        usuario.bloqueado_hasta = hasta
        usuario.save(update_fields=['bloqueado_hasta'])
    Bloqueo.objects.create(
        usuario=usuario, seccion=usuario.seccion, solicitud=solicitud,
        fecha_fin=hasta, motivo='Devolucion atrasada',
    )


def _devolver(solicitud, equipos, items, usuario, datos):
    estado_general = datos.get('estado_equipo') or SolicitudItem.EstadoDevolucion.BUENO
    if estado_general not in ESTADOS_DEVOLUCION:
        raise ValueError('Estado de devolución no válido.')
    atrasada = timezone.now() > solicitud.horario_fin

    estados = {}
    for item in items:
        if item.equipo_id:
            estado = datos.get(f'estado_item_{item.id}') or estado_general
            if estado not in ESTADOS_DEVOLUCION:
                raise ValueError('Estado de devolución no válido.')
            item.estado_devolucion = estado
            item.save(update_fields=['estado_devolucion'])
            estados[item.equipo_id] = estado

    for equipo in equipos:
        if equipo.estado == Equipo.Estado.PRESTADO:
            estado = estados[equipo.id]
            destino = (Equipo.Estado.EN_MANTENIMIENTO if estado in SolicitudItem.ESTADOS_CON_FALLA
                       else Equipo.Estado.DISPONIBLE)
            cambiar_estado_equipo(equipo, usuario, destino, f'Devolución de la solicitud #{solicitud.id} (estado: {estado})')
    for item in items:
        if item.insumo_id and item.insumo.tipo == Insumo.Tipo.RENOVABLE:
            Insumo.objects.filter(id=item.insumo_id).update(
                cantidad_disponible=F('cantidad_disponible') + item.cantidad, version=F('version') + 1,
            )

    solicitud.estado = Solicitud.EstadoSolicitud.DEVUELTA_ATRASO if atrasada else Solicitud.EstadoSolicitud.DEVUELTA
    solicitud.save()
    Movimiento.objects.create(
        solicitud=solicitud,
        tipo=Movimiento.TipoMovimiento.DEVOLUCION,
        responsable=usuario,
        estado_equipo=max(estados.values(), key=ESTADOS_DEVOLUCION.index, default=estado_general),
    )
    if atrasada:
        sancionar(solicitud.beneficiario, solicitud)


@transaction.atomic
def aplicar_accion_solicitud(usuario, solicitud_id, accion, datos=None):
    datos = datos or {}
    if accion not in TRANSICIONES_SOLICITUD:
        raise ValueError('Acción no válida.')
    solicitud = Solicitud.objects.select_for_update().filter(
        id=solicitud_id if str(solicitud_id or '').isdigit() else None,
    ).first()
    if solicitud is None:
        raise ValueError('La solicitud no existe.')
    if accion == 'cancelar' and solicitud.solicitante_id != usuario.id:
        raise ValueError('Solo quien creó la solicitud puede cancelarla.')
    if solicitud.estado not in TRANSICIONES_SOLICITUD[accion]:
        raise ValueError(
            f'No se puede {accion} la solicitud #{solicitud.id} porque está '
            f'{solicitud.get_estado_display().lower()}.'
        )

    items = list(solicitud.items.select_related('insumo'))
    equipos = Equipo.objects.select_for_update().filter(
        id__in=[i.equipo_id for i in items if i.equipo_id]
    ).order_by('id')

    if accion == 'aprobar':
        _aprobar(solicitud, equipos, usuario)
    elif accion == 'entregar':
        _entregar(solicitud, equipos, items, usuario)
    elif accion == 'devolver':
        _devolver(solicitud, equipos, items, usuario, datos)
    elif accion == 'rechazar':
        solicitud.estado = Solicitud.EstadoSolicitud.RECHAZADA
        solicitud.save()
        notificaciones.notificar('rechazada', solicitud)
    elif accion == 'cancelar':
        solicitud.estado = Solicitud.EstadoSolicitud.CANCELADA
        solicitud.save()
    return solicitud


def equipos_diagnosticables():
    return Equipo.objects.filter(estado__in=ESTADOS_DIAGNOSTICABLES).exclude(
        id__in=Mantenimiento.objects.filter(fecha_resolucion__isnull=True).values('equipo_id'),
    )


def sugerir_decision(costo, valor_adquisicion):
    if not valor_adquisicion:
        return Mantenimiento.Decision.REPARAR, None
    proporcion = Decimal(costo) / Decimal(valor_adquisicion)
    sugerencia = Mantenimiento.Decision.DAR_BAJA if proporcion >= UMBRAL_BAJA else Mantenimiento.Decision.REPARAR
    return sugerencia, proporcion.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


@transaction.atomic
def diagnosticar(usuario, equipo_id, falla, costo):
    equipo = Equipo.objects.select_for_update().filter(id=equipo_id).first()
    if equipo is None:
        raise ValueError('El equipo no existe.')
    if equipo.estado not in ESTADOS_DIAGNOSTICABLES:
        raise ValueError(f'El equipo {equipo.nombre} está {equipo.get_estado_display().lower()} y no se puede diagnosticar.')
    if equipo.mantenimientos.filter(fecha_resolucion__isnull=True).exists():
        raise ValueError(f'El equipo {equipo.nombre} ya tiene un mantenimiento abierto.')

    sugerencia, porcentaje = sugerir_decision(costo, equipo.valor_adquisicion)
    mantenimiento = Mantenimiento.objects.create(
        equipo=equipo, falla_descrita=falla, costo_cotizado=Decimal(costo),
        porcentaje_costo=porcentaje, decision=sugerencia, reportado_por=usuario,
    )
    cambiar_estado_equipo(equipo, usuario, Equipo.Estado.EN_MANTENIMIENTO, f'Diagnóstico de mantenimiento #{mantenimiento.id}')
    return mantenimiento


@transaction.atomic
def resolver_mantenimiento(usuario, mant_id, accion):
    if accion not in ACCIONES_MANTENIMIENTO:
        raise ValueError('Acción no válida.')
    mant = Mantenimiento.objects.select_for_update().filter(
        id=mant_id if str(mant_id or '').isdigit() else None,
    ).first()
    if mant is None:
        raise ValueError('El mantenimiento no existe.')
    equipo = Equipo.objects.select_for_update().get(id=mant.equipo_id)
    if mant.fecha_resolucion is not None:
        raise ValueError(f'El mantenimiento #{mant.id} ya fue resuelto.')
    if accion == 'reparar' and mant.decision == Mantenimiento.Decision.REPARAR:
        raise ValueError(f'El mantenimiento #{mant.id} ya está en reparación.')
    if equipo.estado != Equipo.Estado.EN_MANTENIMIENTO:
        raise ValueError(f'El equipo {equipo.nombre} no está en mantenimiento.')

    decision, estado, detalle = ACCIONES_MANTENIMIENTO[accion]
    mant.decision = decision
    if accion != 'reparar':
        mant.fecha_resolucion = timezone.now()
    mant.save()
    cambiar_estado_equipo(equipo, usuario, estado, f'Mantenimiento #{mant.id}: {detalle}')
    mant.equipo = equipo
    return mant


def cambiar_estado_manual(equipo, usuario, nuevo_estado, detalle):
    if nuevo_estado not in Equipo.Estado.values:
        raise ValueError('Estado de equipo no válido.')
    if Equipo.Estado.PRESTADO in (equipo.estado, nuevo_estado):
        raise ValueError('El estado "Prestado" solo cambia mediante la entrega y devolución de solicitudes.')
    cambiar_estado_equipo(equipo, usuario, nuevo_estado, detalle)


def unidades_entregadas(insumo):
    return insumo.cantidad_total - insumo.cantidad_disponible


def aplicar_total_insumo(insumo, entregadas):
    if insumo.cantidad_total < entregadas:
        raise ValueError(f'Hay {entregadas} unidades entregadas; el total no puede ser menor.')
    insumo.cantidad_disponible = insumo.cantidad_total - entregadas
    insumo.version += 1
    insumo.save()
