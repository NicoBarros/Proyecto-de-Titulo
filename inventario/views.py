from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib.auth.views import PasswordChangeView
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib import messages
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Count, Q, F, ProtectedError
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from django.urls import reverse, reverse_lazy
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from datetime import timedelta
import hmac
import json
import io
import logging
import re

import qrcode
import qrcode.image.svg

from .models import (
    Usuario, Equipo, Insumo, Solicitud, SolicitudItem, Movimiento,
    Bloqueo, Mantenimiento, HistorialEquipo, EventoSeguridad, Migracion
)
from .forms import EquipoForm, InsumoForm, MantenimientoForm
from .decorators import role_required
from .exportar import generar_excel_inventario, generar_plantilla_importacion
from .importar import importar_inventario
from . import auditoria, notificaciones, tareas
from .kpi import PERIODOS, calcular_kpis
from .seguridad import registrar_evento

logger = logging.getLogger(__name__)


def _errores_password(password, usuario):
    try:
        validate_password(password, user=usuario)
    except ValidationError as e:
        return ' '.join(e.messages)
    return None


def _registrar_cambio_cuenta(request, objetivo, detalle):
    registrar_evento(EventoSeguridad.Tipo.CAMBIO_CUENTA, request, usuario=request.user, detalle=f'{objetivo.email}: {detalle}')


@login_required
def dashboard_view(request):
    Solicitud.marcar_atrasadas()
    totales = {
        **Equipo.objects.aggregate(
            total_equipos=Count('id'),
            equipos_disponibles=Count('id', filter=Q(estado=Equipo.Estado.DISPONIBLE)),
            equipos_prestados=Count('id', filter=Q(estado=Equipo.Estado.PRESTADO)),
            equipos_mantenimiento=Count('id', filter=Q(estado=Equipo.Estado.EN_MANTENIMIENTO)),
        ),
        **Solicitud.objects.aggregate(
            solicitudes_pendientes=Count('id', filter=Q(estado=Solicitud.EstadoSolicitud.PENDIENTE)),
            solicitudes_atrasadas=Count('id', filter=Q(estado=Solicitud.EstadoSolicitud.ATRASADA)),
        ),
        'insumos_bajo_stock': Insumo.objects.filter(cantidad_disponible__lte=F('umbral_minimo')).count(),
    }
    atrasadas = []
    if request.user.rol in Usuario.ROLES_APROBADORES or request.user.is_superuser:
        atrasadas = (
            Solicitud.objects.filter(estado=Solicitud.EstadoSolicitud.ATRASADA)
            .select_related('solicitante', 'en_representacion_de')
            .prefetch_related('items__equipo', 'items__insumo')
            .order_by('horario_fin')
        )
    return render(request, 'inventario/dashboard.html', {'totales': totales, 'atrasadas': atrasadas})


@login_required
def inventario_view(request):
    puede_escribir = request.user.rol in Usuario.ROLES_ESCRITURA_INVENTARIO
    tab = request.GET.get('tab', 'equipos')
    
    context = {'puede_escribir': puede_escribir, 'tab': tab}
    
    if tab == 'equipos':
        q = request.GET.get('q', '').strip()
        filtro_estado = request.GET.get('estado', '').strip()
        filtro_ubicacion = request.GET.get('ubicacion', '').strip()
        orden = request.GET.get('orden', 'nombre')

        qs = Equipo.objects.all()

        if q:
            qs = qs.filter(
                Q(codigo_inventario__icontains=q) |
                Q(nombre__icontains=q) |
                Q(modelo__icontains=q) |
                Q(especificaciones__icontains=q) |
                Q(ubicacion__icontains=q)
            )

        if filtro_estado:
            qs = qs.filter(estado=filtro_estado)

        if filtro_ubicacion:
            qs = qs.filter(ubicacion__icontains=filtro_ubicacion)

        orden_map = {
            'nombre': 'nombre',
            '-nombre': '-nombre',
            'codigo': 'codigo_inventario',
            '-codigo': '-codigo_inventario',
            'estado': 'estado',
            '-estado': '-estado',
            '-valor': '-valor_adquisicion',
            'valor': 'valor_adquisicion',
            '-recientes': '-created_at',
        }
        qs = qs.order_by(orden_map.get(orden, 'nombre'))

        ubicaciones = Equipo.objects.exclude(ubicacion__isnull=True).exclude(ubicacion='').values_list('ubicacion', flat=True).distinct()

        total_filtrados = qs.count()
        paginator = Paginator(qs, 25)
        page_obj = paginator.get_page(request.GET.get('page'))

        context['equipos'] = page_obj
        context['page_obj'] = page_obj
        context['paginator'] = paginator
        context['total_equipos_filtrados'] = total_filtrados
        context['total_equipos_general'] = Equipo.objects.count()
        context['q'] = q
        context['filtro_estado'] = filtro_estado
        context['filtro_ubicacion'] = filtro_ubicacion
        context['orden'] = orden
        context['estados_choices'] = Equipo.Estado.choices
        context['ubicaciones'] = sorted(list(set(ubicaciones)))

        if puede_escribir and request.method == 'POST' and 'codigo_inventario' in request.POST:
            form = EquipoForm(request.POST)
            if form.is_valid():
                equipo = form.save()
                auditoria.registrar(equipo, request.user, HistorialEquipo.Accion.CREADO)
                messages.success(request, 'Equipo agregado exitosamente.')
                return redirect('/inventario/?tab=equipos')
            else:
                messages.error(request, 'Error al agregar equipo.')
    else:
        q_insumo = request.GET.get('q_insumo', '').strip()
        filtro_categoria = request.GET.get('categoria', '').strip()
        filtro_tipo = request.GET.get('tipo', '').strip()
        filtro_stock = request.GET.get('stock', '').strip()

        qs = Insumo.objects.all()

        if q_insumo:
            qs = qs.filter(
                Q(nombre__icontains=q_insumo) |
                Q(categoria__icontains=q_insumo)
            )

        if filtro_categoria:
            qs = qs.filter(categoria__icontains=filtro_categoria)

        if filtro_tipo:
            qs = qs.filter(tipo=filtro_tipo)

        if filtro_stock == 'bajo':
            qs = qs.filter(cantidad_disponible__lte=F('umbral_minimo'))
        elif filtro_stock == 'agotado':
            qs = qs.filter(cantidad_disponible=0)
        elif filtro_stock == 'disponible':
            qs = qs.filter(cantidad_disponible__gt=0)

        categorias = Insumo.objects.exclude(categoria__isnull=True).exclude(categoria='').values_list('categoria', flat=True).distinct()

        total_insumos_filtrados = qs.count()
        paginator_insumos = Paginator(qs, 25)
        page_obj_insumos = paginator_insumos.get_page(request.GET.get('page_insumo'))

        context['insumos'] = page_obj_insumos
        context['page_obj_insumos'] = page_obj_insumos
        context['paginator_insumos'] = paginator_insumos
        context['total_insumos_filtrados'] = total_insumos_filtrados
        context['total_insumos_general'] = Insumo.objects.count()
        context['q_insumo'] = q_insumo
        context['filtro_categoria'] = filtro_categoria
        context['filtro_tipo'] = filtro_tipo
        context['filtro_stock'] = filtro_stock
        context['tipos_choices'] = Insumo.Tipo.choices
        context['categorias'] = sorted(list(set(categorias)))

        if puede_escribir and request.method == 'POST' and 'cantidad_total' in request.POST:
            form = InsumoForm(request.POST)
            if form.is_valid():
                insumo = form.save(commit=False)
                insumo.cantidad_disponible = insumo.cantidad_total
                insumo.save()
                messages.success(request, 'Insumo agregado exitosamente.')
                return redirect('/inventario/?tab=insumos')
            else:
                messages.error(request, 'Error al agregar insumo.')
                
    return render(request, 'inventario/inventario.html', context)


@login_required
@role_required(Usuario.Rol.ENCARGADO_LABORATORIO, Usuario.Rol.CONTROL_CALIDAD)
def eliminar_equipo(request, id):
    equipo = get_object_or_404(Equipo, id=id)
    if request.method == 'POST':
        if equipo.estado not in [Equipo.Estado.DISPONIBLE, Equipo.Estado.FUERA_SERVICIO]:
            messages.error(request, 'No puedes eliminar un equipo que está prestado o en mantenimiento.')
        else:
            try:
                with transaction.atomic():
                    auditoria.registrar(equipo, request.user, HistorialEquipo.Accion.ELIMINADO)
                    equipo.delete()
                messages.success(request, 'Equipo eliminado exitosamente.')
            except ProtectedError:
                messages.error(request, 'El equipo tiene préstamos o mantenimientos registrados y no se puede eliminar. '
                                        'Márcalo como "Fuera de servicio" para conservar su historial.')
    return redirect('/inventario/?tab=equipos')


@login_required
@role_required(Usuario.Rol.ENCARGADO_LABORATORIO, Usuario.Rol.CONTROL_CALIDAD)
def editar_equipo(request, id):
    equipo = get_object_or_404(Equipo, id=id)
    if request.method == 'POST':
        antes = auditoria.foto(equipo)
        form = EquipoForm(request.POST, instance=equipo)
        if form.is_valid():
            equipo = form.save(commit=False)
            equipo.version += 1
            equipo.save()
            auditoria.registrar(equipo, request.user, HistorialEquipo.Accion.EDITADO, antes)
            messages.success(request, 'Equipo actualizado exitosamente.')
            return redirect('/inventario/?tab=equipos')
    else:
        form = EquipoForm(instance=equipo)
    return render(request, 'inventario/editar_equipo.html', {'form': form, 'equipo': equipo})


@login_required
@role_required(Usuario.Rol.ENCARGADO_LABORATORIO, Usuario.Rol.CONTROL_CALIDAD)
def historial_equipo(request, id):
    equipo = get_object_or_404(Equipo, id=id)
    registros = list(equipo.historial.select_related('usuario'))
    for r in registros:
        r.lista_cambios = [
            (auditoria.CAMPOS_AUDITADOS.get(campo, campo),
             auditoria.etiqueta_valor(campo, valores[0]),
             auditoria.etiqueta_valor(campo, valores[1]))
            for campo, valores in r.cambios.items()
        ]
    return render(request, 'inventario/historial_equipo.html', {'equipo': equipo, 'registros': registros})


@login_required
def ficha_equipo(request, id):
    equipo = get_object_or_404(Equipo, id=id)
    gestiona = request.user.rol in Usuario.ROLES_ESCRITURA_INVENTARIO
    ve_tecnico = gestiona or request.user.rol in Usuario.ROLES_APROBADORES
    reservas = (
        SolicitudItem.objects.filter(
            equipo=equipo, solicitud__horario_fin__gte=timezone.now(),
            solicitud__estado__in=[Solicitud.EstadoSolicitud.APROBADA, *Solicitud.ESTADOS_EN_PRESTAMO],
        )
        .select_related('solicitud')
        .order_by('solicitud__horario_inicio')[:10]
    )
    contexto = {
        'equipo': equipo,
        'reservas': reservas,
        'gestiona': gestiona,
        've_tecnico': ve_tecnico,
        'puede_solicitar': equipo.estado == Equipo.Estado.DISPONIBLE,
    }
    if ve_tecnico:
        contexto['mantenimientos'] = equipo.mantenimientos.select_related('reportado_por')[:5]
        contexto['devoluciones'] = (
            SolicitudItem.objects.filter(equipo=equipo).exclude(estado_devolucion='')
            .select_related('solicitud').order_by('-solicitud__horario_fin')[:5]
        )
    if gestiona:
        contexto['historial'] = equipo.historial.select_related('usuario')[:5]
    return render(request, 'inventario/ficha_equipo.html', contexto)


@login_required
@role_required(Usuario.Rol.ENCARGADO_LABORATORIO, Usuario.Rol.CONTROL_CALIDAD)
def qr_equipo(request, id):
    equipo = get_object_or_404(Equipo, id=id)
    imagen = qrcode.make(
        f"{settings.URL_SITIO}{reverse('ficha_equipo', args=[equipo.id])}",
        image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2,
    )
    salida = io.BytesIO()
    imagen.save(salida)
    response = HttpResponse(salida.getvalue(), content_type='image/svg+xml')
    if request.GET.get('descargar'):
        response['Content-Disposition'] = f'attachment; filename="qr_{equipo.codigo_inventario}.svg"'
    return response


@login_required
@role_required(Usuario.Rol.ENCARGADO_LABORATORIO, Usuario.Rol.CONTROL_CALIDAD)
def eliminar_insumo(request, id):
    insumo = get_object_or_404(Insumo, id=id)
    if request.method == 'POST':
        try:
            insumo.delete()
            messages.success(request, 'Insumo eliminado exitosamente.')
        except ProtectedError:
            messages.error(request, 'El insumo aparece en solicitudes registradas y no se puede eliminar.')
    return redirect('/inventario/?tab=insumos')


@login_required
@role_required(Usuario.Rol.ENCARGADO_LABORATORIO, Usuario.Rol.CONTROL_CALIDAD)
def editar_insumo(request, id):
    insumo = get_object_or_404(Insumo, id=id)
    if request.method == 'POST':
        with transaction.atomic():
            insumo = get_object_or_404(Insumo.objects.select_for_update(), id=id)
            total_anterior = insumo.cantidad_total
            form = InsumoForm(request.POST, instance=insumo)
            if form.is_valid():
                insumo_editado = form.save(commit=False)
                en_uso = total_anterior - insumo_editado.cantidad_disponible
                if insumo_editado.cantidad_total < en_uso:
                    form.add_error('cantidad_total', f'Hay {en_uso} unidades entregadas; el total no puede ser menor.')
                else:
                    insumo_editado.cantidad_disponible = insumo_editado.cantidad_total - en_uso
                    insumo_editado.version += 1
                    insumo_editado.save()
                    messages.success(request, 'Insumo actualizado exitosamente.')
                    return redirect('/inventario/?tab=insumos')
    else:
        form = InsumoForm(instance=insumo)
    return render(request, 'inventario/editar_insumo.html', {'form': form, 'insumo': insumo})

def _parse_fecha(valor):
    """Convierte el valor de un <input type="datetime-local"> en datetime con zona horaria."""
    fecha = parse_datetime(valor or '')
    if fecha is None:
        return None
    if timezone.is_naive(fecha):
        fecha = timezone.make_aware(fecha)
    return fecha

TRANSICIONES_SOLICITUD = {
    'aprobar': [Solicitud.EstadoSolicitud.PENDIENTE],
    'rechazar': [Solicitud.EstadoSolicitud.PENDIENTE, Solicitud.EstadoSolicitud.APROBADA],
    'entregar': [Solicitud.EstadoSolicitud.APROBADA],
    'devolver': Solicitud.ESTADOS_EN_PRESTAMO,
    'cancelar': [Solicitud.EstadoSolicitud.PENDIENTE, Solicitud.EstadoSolicitud.APROBADA],
}

MENSAJES_ACCION = {
    'aprobar': 'aprobada',
    'rechazar': 'rechazada',
    'entregar': 'entregada',
    'devolver': 'devuelta',
    'cancelar': 'cancelada',
}

ESTADOS_DEVOLUCION = SolicitudItem.EstadoDevolucion.values


def _ejecutar_accion_solicitud(request, solicitud_id, accion):
    """Aplica aprobar/rechazar/entregar/devolver. Debe llamarse dentro de transaction.atomic()."""
    solicitud = get_object_or_404(Solicitud.objects.select_for_update(), id=solicitud_id)
    if accion not in TRANSICIONES_SOLICITUD:
        raise ValueError('Acción no válida.')
    if accion == 'cancelar' and solicitud.solicitante_id != request.user.id:
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
        for equipo in equipos:
            if equipo.estado in (Equipo.Estado.EN_MANTENIMIENTO, Equipo.Estado.FUERA_SERVICIO):
                raise ValueError(f'El equipo {equipo.nombre} está {equipo.get_estado_display().lower()}.')
            choque = SolicitudItem.objects.filter(
                equipo=equipo,
                solicitud__estado__in=[Solicitud.EstadoSolicitud.APROBADA, *Solicitud.ESTADOS_EN_PRESTAMO]
            ).exclude(solicitud=solicitud).filter(
                Q(solicitud__horario_inicio__lt=solicitud.horario_fin) &
                Q(solicitud__horario_fin__gt=solicitud.horario_inicio)
            ).exists()
            if choque:
                raise ValueError(f'El equipo {equipo} ya esta reservado en ese horario.')

        solicitud.estado = Solicitud.EstadoSolicitud.APROBADA
        solicitud.aprobado_por = request.user
        solicitud.fecha_aprobacion = timezone.now()
        solicitud.save()
        notificaciones.notificar('aprobada', solicitud)

    elif accion == 'entregar':
        for equipo in equipos:
            if equipo.estado != Equipo.Estado.DISPONIBLE:
                raise ValueError(f'El equipo {equipo.nombre} no está disponible para entregar.')
            antes = auditoria.foto(equipo)
            equipo.estado = Equipo.Estado.PRESTADO
            equipo.version += 1
            equipo.save(update_fields=['estado', 'version', 'updated_at'])
            auditoria.registrar(equipo, request.user, HistorialEquipo.Accion.ESTADO, antes, f'Entrega de la solicitud #{solicitud.id}')
        for item in items:
            if item.insumo_id:
                actualizados = Insumo.objects.filter(
                    id=item.insumo_id, cantidad_disponible__gte=item.cantidad,
                ).update(cantidad_disponible=F('cantidad_disponible') - item.cantidad, version=F('version') + 1)
                if not actualizados:
                    raise ValueError(f'Stock insuficiente para {item.insumo.nombre}.')

        solicitud.estado = Solicitud.EstadoSolicitud.ENTREGADA
        solicitud.save()
        Movimiento.objects.create(solicitud=solicitud, tipo=Movimiento.TipoMovimiento.ENTREGA, responsable=request.user)

    elif accion == 'devolver':
        estado_general = request.POST.get('estado_equipo') or SolicitudItem.EstadoDevolucion.BUENO
        if estado_general not in ESTADOS_DEVOLUCION:
            raise ValueError('Estado de devolución no válido.')
        atrasada = timezone.now() > solicitud.horario_fin

        estados = {}
        for item in items:
            if item.equipo_id:
                estado = request.POST.get(f'estado_item_{item.id}') or estado_general
                if estado not in ESTADOS_DEVOLUCION:
                    raise ValueError('Estado de devolución no válido.')
                item.estado_devolucion = estado
                item.save(update_fields=['estado_devolucion'])
                estados[item.equipo_id] = estado

        for equipo in equipos:
            if equipo.estado == Equipo.Estado.PRESTADO:
                estado = estados[equipo.id]
                antes = auditoria.foto(equipo)
                equipo.estado = (Equipo.Estado.EN_MANTENIMIENTO if estado in SolicitudItem.ESTADOS_CON_FALLA
                                 else Equipo.Estado.DISPONIBLE)
                equipo.version += 1
                equipo.save(update_fields=['estado', 'version', 'updated_at'])
                auditoria.registrar(equipo, request.user, HistorialEquipo.Accion.ESTADO, antes,
                                    f'Devolución de la solicitud #{solicitud.id} (estado: {estado})')
        estado_equipo = max(estados.values(), key=ESTADOS_DEVOLUCION.index, default=estado_general)
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
            responsable=request.user,
            estado_equipo=estado_equipo,
        )

        if atrasada:
            usuario = solicitud.en_representacion_de or solicitud.solicitante
            hasta = timezone.now() + timedelta(days=7)
            if not usuario.bloqueado_hasta or usuario.bloqueado_hasta < hasta:
                usuario.bloqueado_hasta = hasta
                usuario.save(update_fields=['bloqueado_hasta'])
            Bloqueo.objects.create(
                usuario=usuario, seccion=usuario.seccion, solicitud=solicitud,
                fecha_fin=hasta, motivo='Devolucion atrasada'
            )

    elif accion == 'rechazar':
        solicitud.estado = Solicitud.EstadoSolicitud.RECHAZADA
        solicitud.save()
        notificaciones.notificar('rechazada', solicitud)

    elif accion == 'cancelar':
        solicitud.estado = Solicitud.EstadoSolicitud.CANCELADA
        solicitud.save()


@login_required
def solicitudes_view(request):
    Solicitud.marcar_atrasadas()
    puede_aprobar = (
        request.user.rol in Usuario.ROLES_APROBADORES or
        request.user.is_superuser
    )
    puede_representar = request.user.rol in Usuario.ROLES_REPRESENTANTES
    if request.method == 'POST' and 'item[]' in request.POST:
        items = request.POST.getlist('item[]')
        cantidades = request.POST.getlist('cantidad[]')

        try:
            if request.user.esta_bloqueado():
                hasta = timezone.localtime(request.user.bloqueado_hasta).strftime('%d-%m-%Y %H:%M')
                raise ValueError(f'Tu cuenta está bloqueada para solicitar préstamos hasta el {hasta}.')

            representado = None
            representado_id = (request.POST.get('en_representacion_de') or '').strip()
            if representado_id:
                if not puede_representar:
                    raise ValueError('Tu rol no permite solicitar en representación de un estudiante.')
                representado = Usuario.objects.filter(
                    id=representado_id if representado_id.isdigit() else None,
                    rol=Usuario.Rol.ESTUDIANTE, is_active=True,
                ).first()
                if representado is None:
                    raise ValueError('El estudiante seleccionado no es válido.')
                if representado.esta_bloqueado():
                    hasta = timezone.localtime(representado.bloqueado_hasta).strftime('%d-%m-%Y %H:%M')
                    raise ValueError(f'{representado.get_full_name() or representado.email} está bloqueado para préstamos hasta el {hasta}.')

            beneficiario = representado or request.user
            if beneficiario.tiene_atrasos():
                if representado:
                    raise ValueError(f'{representado.get_full_name() or representado.email} tiene préstamos atrasados sin devolver.')
                raise ValueError('Tienes préstamos atrasados sin devolver. Devuélvelos antes de crear una nueva solicitud.')

            inicio = _parse_fecha(request.POST.get('horario_inicio'))
            fin = _parse_fecha(request.POST.get('horario_fin'))
            if inicio is None or fin is None:
                raise ValueError('Debes indicar un horario de inicio y de fin válidos.')
            if fin <= inicio:
                raise ValueError('El horario de fin debe ser posterior al de inicio.')

            lugar_uso = request.POST.get('lugar_uso') or Solicitud.LugarUso.DENTRO_SEDE
            if lugar_uso not in Solicitud.LugarUso.values:
                raise ValueError('Lugar de uso no válido.')

            with transaction.atomic():
                solicitud = Solicitud.objects.create(
                    solicitante=request.user,
                    en_representacion_de=representado,
                    lugar_uso=lugar_uso,
                    justificacion=request.POST.get('justificacion'),
                    horario_inicio=inicio,
                    horario_fin=fin,
                )
                

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

                for item_id in equipos_ids:
                    equipo = get_object_or_404(Equipo, id=item_id)
                    if equipo.estado != Equipo.Estado.DISPONIBLE:
                        raise ValueError(f'El equipo {equipo.nombre} no se encuentra disponible actualmente.')
                    SolicitudItem.objects.create(solicitud=solicitud, equipo=equipo, cantidad=1)
                for item_id, cantidad in insumos_cant.items():
                    insumo = get_object_or_404(Insumo, id=item_id)
                    if insumo.cantidad_disponible < cantidad:
                        raise ValueError(f'No hay stock suficiente para {insumo.nombre}. Disponible: {insumo.cantidad_disponible}.')
                    SolicitudItem.objects.create(solicitud=solicitud, insumo=insumo, cantidad=cantidad)

                messages.success(request, 'Solicitud (Kit) creada correctamente.')
        except ValueError as e:
            messages.error(request, str(e))
            
        return redirect('solicitudes')

    if request.method == 'POST' and 'accion' in request.POST:
        accion = request.POST.get('accion')
        if not puede_aprobar and accion != 'cancelar':
            messages.error(request, 'No tienes permiso para aprobar solicitudes.')
            return redirect('solicitudes')

        try:
            with transaction.atomic():
                _ejecutar_accion_solicitud(request, request.POST.get('solicitud_id'), accion)
            messages.success(request, f'Solicitud {MENSAJES_ACCION[accion]} correctamente.')
        except ValueError as e:
            messages.error(request, str(e))

        return redirect('solicitudes')

    solicitudes = (
        Solicitud.objects.all()
        .select_related('solicitante', 'en_representacion_de')
        .prefetch_related('items', 'items__equipo', 'items__insumo')
    )
    if not puede_aprobar:
        solicitudes = solicitudes.filter(Q(solicitante=request.user) | Q(en_representacion_de=request.user))
    solicitudes = Paginator(solicitudes, 20).get_page(request.GET.get('page'))
    equipos = Equipo.objects.filter(estado=Equipo.Estado.DISPONIBLE)
    insumos = Insumo.objects.all()
    estudiantes = []
    if puede_representar:
        estudiantes = Usuario.objects.filter(rol=Usuario.Rol.ESTUDIANTE, is_active=True).order_by('first_name', 'email')

    return render(request, 'inventario/solicitudes.html', {
        'solicitudes': solicitudes, 'equipos': equipos, 'insumos': insumos, 'puede_aprobar': puede_aprobar,
        'equipo_preseleccionado': request.GET.get('equipo', ''),
        'estudiantes': estudiantes, 'ahora': timezone.now(),
    })


ACCIONES_MANTENIMIENTO = {
    'completar_reparacion': (Mantenimiento.Decision.COMPLETADO, Equipo.Estado.DISPONIBLE, 'reparación completada'),
    'completado': (Mantenimiento.Decision.COMPLETADO, Equipo.Estado.DISPONIBLE, 'reparación completada'),
    'dar_baja': (Mantenimiento.Decision.DAR_BAJA, Equipo.Estado.FUERA_SERVICIO, 'dado de baja'),
    'reparar': (Mantenimiento.Decision.REPARAR, Equipo.Estado.EN_MANTENIMIENTO, 'en reparación'),
}

ESTADOS_DIAGNOSTICABLES = [Equipo.Estado.DISPONIBLE, Equipo.Estado.EN_MANTENIMIENTO]


def _resolver_mantenimiento(request, mant_id, accion):
    if accion not in ACCIONES_MANTENIMIENTO:
        raise ValueError('Acción no válida.')
    mant = get_object_or_404(Mantenimiento.objects.select_for_update(), id=mant_id)
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

    if equipo.estado != estado:
        antes = auditoria.foto(equipo)
        equipo.estado = estado
        equipo.version += 1
        equipo.save()
        auditoria.registrar(equipo, request.user, HistorialEquipo.Accion.ESTADO, antes, f'Mantenimiento #{mant.id}: {detalle}')
    return mant, equipo


def _diagnosticar(request, form):
    equipo = get_object_or_404(Equipo.objects.select_for_update(), id=form.cleaned_data['equipo_id'])
    if equipo.estado not in ESTADOS_DIAGNOSTICABLES:
        raise ValueError(f'El equipo {equipo.nombre} está {equipo.get_estado_display().lower()} y no se puede diagnosticar.')
    if equipo.mantenimientos.filter(fecha_resolucion__isnull=True).exists():
        raise ValueError(f'El equipo {equipo.nombre} ya tiene un mantenimiento abierto.')

    costo = Decimal(form.cleaned_data['costo_cotizado'])
    if equipo.valor_adquisicion:
        proporcion = costo / Decimal(equipo.valor_adquisicion)
        porcentaje = proporcion.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    else:
        proporcion = porcentaje = None

    sugerencia = (
        Mantenimiento.Decision.DAR_BAJA
        if proporcion is not None and proporcion >= Decimal('0.70')
        else Mantenimiento.Decision.REPARAR
    )

    antes = auditoria.foto(equipo)
    mantenimiento = Mantenimiento.objects.create(
        equipo=equipo,
        falla_descrita=form.cleaned_data['falla_descrita'],
        costo_cotizado=costo,
        porcentaje_costo=porcentaje,
        decision=sugerencia,
        reportado_por=request.user
    )
    if equipo.estado != Equipo.Estado.EN_MANTENIMIENTO:
        equipo.estado = Equipo.Estado.EN_MANTENIMIENTO
        equipo.version += 1
        equipo.save()
        auditoria.registrar(equipo, request.user, HistorialEquipo.Accion.ESTADO, antes, f'Diagnóstico de mantenimiento #{mantenimiento.id}')
    return sugerencia, porcentaje


@login_required
@role_required(Usuario.Rol.ENCARGADO_LABORATORIO, Usuario.Rol.CONTROL_CALIDAD, Usuario.Rol.DIRECTOR_CARRERA)
def mantenimiento_view(request):
    if request.method == 'POST':
        try:
            if 'mant_id' in request.POST or 'decision' in request.POST or 'accion_mant' in request.POST:
                accion = request.POST.get('accion_mant') or request.POST.get('decision')
                with transaction.atomic():
                    mant, equipo = _resolver_mantenimiento(request, request.POST.get('mant_id'), accion)
                if mant.decision == Mantenimiento.Decision.COMPLETADO:
                    messages.success(request, f'Reparación completada. "{equipo.nombre}" ({equipo.codigo_inventario}) está disponible.')
                elif mant.decision == Mantenimiento.Decision.DAR_BAJA:
                    messages.warning(request, f'El equipo "{equipo.nombre}" fue dado de baja (Fuera de servicio).')
                else:
                    messages.info(request, f'El equipo "{equipo.nombre}" quedó en reparación.')
            else:
                form = MantenimientoForm(request.POST)
                if not form.is_valid():
                    raise ValueError('Revisa los datos del diagnóstico.')
                with transaction.atomic():
                    sugerencia, porcentaje = _diagnosticar(request, form)
                msg = f'Diagnóstico registrado. Sugerencia: {sugerencia.label.upper()}'
                if porcentaje is not None:
                    msg += f' ({(porcentaje * 100):.1f}% del valor de adquisición).'
                else:
                    msg += ' (sin valor de adquisición registrado).'
                messages.info(request, msg)
        except ValueError as e:
            messages.error(request, str(e))
        return redirect('mantenimiento')

    mantenimientos = Mantenimiento.objects.all().select_related('equipo')
    equipos = Equipo.objects.filter(estado__in=ESTADOS_DIAGNOSTICABLES).exclude(
        id__in=Mantenimiento.objects.filter(fecha_resolucion__isnull=True).values('equipo_id'),
    )
    return render(request, 'inventario/mantenimiento.html', {'mantenimientos': mantenimientos, 'equipos': equipos})


@login_required
def reportes_view(request):
    """RF-13: Reportes (Restringido para Estudiantes y Docentes)."""
    if request.user.rol not in Usuario.ROLES_REPORTES and not request.user.is_superuser:
        messages.error(request, 'Acceso denegado: Los estudiantes y docentes no tienen autorización para ver Reportes y KPIs.')
        return redirect('dashboard')

    top_equipos = Equipo.objects.annotate(veces=Count('solicituditem')).order_by('-veces')[:20]
    Solicitud.marcar_atrasadas()
    vencidos = Solicitud.objects.filter(estado=Solicitud.EstadoSolicitud.ATRASADA).select_related('solicitante', 'en_representacion_de')
    
    dias_str = request.GET.get('dias', '90')
    dias = min(int(dias_str), 3650) if dias_str.isdigit() else 90
    fecha_limite = timezone.now() - timedelta(days=dias)
    sin_movimiento = Equipo.objects.exclude(
        solicituditem__solicitud__created_at__gte=fecha_limite
    )
    
    periodo_str = request.GET.get('periodo', '30')
    periodo = int(periodo_str) if periodo_str.isdigit() and int(periodo_str) in PERIODOS else 30
    kpis = calcular_kpis(periodo)

    return render(request, 'inventario/reportes.html', {
        'top_equipos': top_equipos, 'vencidos': vencidos, 'sin_movimiento': sin_movimiento, 'dias': dias,
        'kpis': kpis, 'periodo': periodo, 'periodos': PERIODOS,
        'kpis_cumplidos': sum(1 for k in kpis if k.cumple),
        'kpis_medidos': sum(1 for k in kpis if k.cumple is not None),
    })

def _cupo_ia_disponible(usuario):
    clave = f'ia_consultas:{usuario.pk}:{timezone.now():%Y%m%d%H}'
    cache.add(clave, 0, 3600)
    return cache.incr(clave) <= settings.IA_CONSULTAS_POR_HORA


@login_required
def busqueda_view(request):
    if request.method == 'GET':
        return render(request, 'inventario/busqueda.html')
        
    consulta = request.POST.get('consulta')
    disponibles = list(Equipo.objects.filter(estado=Equipo.Estado.DISPONIBLE))
    
    if not consulta:
        return JsonResponse({'error': 'Falta consulta'}, status=400)
        
    resultados = []
    fuente = 'palabras_clave_local'
    
    if settings.GEMINI_API_KEY and _cupo_ia_disponible(request.user):
        try:
            from google import genai
            from google.genai.errors import APIError
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            
            catalogo = "\n".join([f"- id={e.id}: {e.nombre} ({e.modelo or 's/modelo'}) - {e.especificaciones or ''}" for e in disponibles])
            prompt = f"""Eres un asistente que ayuda a un encargado de laboratorio a encontrar equipos.
Catalogo de equipos disponibles:
{catalogo}

Necesidad del usuario: "{consulta}"

Responde SOLO con un JSON array de los ids de equipo mas relevantes (maximo 5), ordenados del mas al menos relevante. Ejemplo: [3, 1, 7]"""

            try:
                response = client.models.generate_content(
                    model=settings.GEMINI_MODELO,
                    contents=prompt,
                )
            except APIError as e:
                if e.code == 503 or "503" in str(e):
                    response = client.models.generate_content(
                        model=settings.GEMINI_MODELO_RESPALDO,
                        contents=prompt,
                    )
                else:
                    raise e  

            text = response.text.replace('```json', '').replace('```', '').strip()
            match = re.search(r'\[[\d,\s]*\]', text)
            if match:
                text = match.group(0)
            ids = json.loads(text)
            
            if isinstance(ids, list):
                for item_id in ids:
                    equipo = next((e for e in disponibles if e.id == item_id), None)
                    if equipo:
                        resultados.append({
                            'nombre': equipo.nombre, 
                            'codigo_inventario': equipo.codigo_inventario, 
                            'estado': equipo.get_estado_display()
                        })
                fuente = 'ia_gemini'
                
        except Exception as e:
         
            logger.warning('Falló la IA de Gemini (%s). Cayendo a búsqueda local.', e)
            
   
    if not resultados:
        terminos = consulta.lower().split()
        for e in disponibles:
            texto = f"{e.nombre} {e.modelo or ''} {e.especificaciones or ''}".lower()
            score = sum(1 for t in terminos if t in texto)
            if score > 0:
                e.score = score
                
        disp_con_score = [e for e in disponibles if hasattr(e, 'score')]
        disp_con_score.sort(key=lambda x: x.score, reverse=True)
        
        for e in disp_con_score[:5]:
            resultados.append({
                'nombre': e.nombre, 
                'codigo_inventario': e.codigo_inventario, 
                'estado': e.get_estado_display()
            })
            
    return JsonResponse({'fuente': fuente, 'resultados': resultados})


@login_required
@role_required(Usuario.Rol.ENCARGADO_LABORATORIO, Usuario.Rol.CONTROL_CALIDAD)
def importar_inventario_view(request):
    if request.method == 'POST':
        archivo = request.FILES.get('archivo')
        if not archivo or not archivo.name.lower().endswith('.xlsx'):
            messages.error(request, 'Selecciona un archivo Excel (.xlsx).')
        elif archivo.size > 5 * 1024 * 1024:
            messages.error(request, 'El archivo supera el máximo de 5 MB.')
        else:
            try:
                migracion = importar_inventario(archivo, request.user)
            except ValueError as e:
                messages.error(request, str(e))
            else:
                if migracion.filas_con_error:
                    messages.warning(
                        request,
                        f'Se importaron {migracion.filas_importadas} de {migracion.filas_totales} filas. '
                        f'{migracion.filas_con_error} con errores.',
                    )
                else:
                    messages.success(request, f'Se importaron {migracion.filas_importadas} filas correctamente.')
                return redirect(f"{reverse('importar_inventario')}?detalle={migracion.id}")
        return redirect('importar_inventario')

    importaciones = Migracion.objects.select_related('ejecutado_por')[:10]
    detalle = None
    if request.GET.get('detalle', '').isdigit():
        detalle = Migracion.objects.filter(id=request.GET['detalle']).first()
    return render(request, 'inventario/importar.html', {
        'importaciones': importaciones,
        'detalle': detalle,
        'errores': detalle.detalle_errores.splitlines() if detalle and detalle.detalle_errores else [],
    })


@login_required
@role_required(Usuario.Rol.ENCARGADO_LABORATORIO, Usuario.Rol.CONTROL_CALIDAD)
def plantilla_importacion(request):
    response = HttpResponse(
        generar_plantilla_importacion(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="plantilla_inventario_leica.xlsx"'
    return response


@login_required
@role_required(Usuario.Rol.ENCARGADO_LABORATORIO, Usuario.Rol.CONTROL_CALIDAD)
def exportar_inventario(request):
    """Genera y descarga un Excel del inventario (Equipos e Insumos) automáticamente."""
    response = HttpResponse(
        generar_excel_inventario(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="inventario_leica_{timezone.localtime().strftime("%Y%m%d")}.xlsx"'
    return response


@login_required
def admin_panel_view(request):
    """Panel de Administración Integrado institucional (no el admin genérico de Django)."""
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, 'Acceso denegado: este panel es exclusivo para administradores del sistema.')
        return redirect('dashboard')

    if request.method == 'POST':
        accion = request.POST.get('accion')

        for campo in ('user_id', 'equipo_id'):
            if campo in request.POST and not request.POST[campo].isdigit():
                messages.error(request, 'Identificador no válido.')
                return redirect('admin_panel')

        if not request.user.is_superuser:
            if accion in ('cambiar_rol', 'toggle_activo', 'desbloquear', 'reset_password'):
                objetivo = get_object_or_404(Usuario, id=request.POST.get('user_id'))
                if objetivo != request.user and (objetivo.is_staff or objetivo.is_superuser):
                    messages.error(request, 'Solo un superusuario puede modificar la cuenta de otro administrador.')
                    return redirect('admin_panel')
                if objetivo == request.user and accion in ('cambiar_rol', 'desbloquear'):
                    messages.error(request, 'No puedes cambiar tu propio rol ni quitarte una sanción.')
                    return redirect('admin_panel')
            rol_pedido = request.POST.get('nuevo_rol') if accion == 'cambiar_rol' else request.POST.get('rol')
            if accion in ('cambiar_rol', 'crear_usuario') and rol_pedido in Usuario.ROLES_APROBADORES:
                messages.error(request, 'Solo un superusuario puede asignar roles con permisos de aprobación.')
                return redirect('admin_panel')

        if accion == 'crear_usuario':
            email = request.POST.get('email', '').strip().lower()
            nombre = request.POST.get('first_name', '').strip()
            apellido = request.POST.get('last_name', '').strip()
            rol = request.POST.get('rol')
            seccion = request.POST.get('seccion', '').strip()
            password = request.POST.get('password', '')
            es_staff = request.POST.get('is_staff') == 'on' and request.user.is_superuser

            dominio = getattr(settings, 'DOMINIO_INSTITUCIONAL', 'inacapmail.cl')
            if not email.endswith(f"@{dominio}") and not email.endswith('@inacapmail.cl'):
                messages.error(request, f'El correo debe pertenecer al dominio institucional (@{dominio}).')
            elif rol not in Usuario.Rol.values:
                messages.error(request, 'Rol no válido.')
            elif Usuario.objects.filter(email=email).exists():
                messages.error(request, f'Ya existe un usuario registrado con el correo {email}.')
            elif error_password := _errores_password(password, Usuario(email=email, first_name=nombre, last_name=apellido)):
                messages.error(request, error_password)
            else:
                username = email.split('@')[0]
                base_username = username
                counter = 1
                while Usuario.objects.filter(username=username).exists():
                    username = f"{base_username}_{counter}"
                    counter += 1

                user = Usuario.objects.create_user(
                    username=username,
                    email=email,
                    first_name=nombre,
                    last_name=apellido,
                    rol=rol,
                    seccion=seccion,
                    password=password,
                    is_staff=es_staff,
                )
                _registrar_cambio_cuenta(request, user, f'cuenta creada con rol {user.get_rol_display()}' + (' (staff)' if es_staff else ''))
                messages.success(request, f'Usuario {user.email} ({user.get_rol_display()}) creado exitosamente.')

        elif accion == 'cambiar_rol':
            user_id = request.POST.get('user_id')
            nuevo_rol = request.POST.get('nuevo_rol')
            user_obj = get_object_or_404(Usuario, id=user_id)
            if nuevo_rol not in Usuario.Rol.values:
                messages.error(request, 'Rol no válido.')
            else:
                rol_anterior = user_obj.get_rol_display()
                user_obj.rol = nuevo_rol
                user_obj.save(update_fields=['rol'])
                _registrar_cambio_cuenta(request, user_obj, f'rol {rol_anterior} → {user_obj.get_rol_display()}')
                messages.success(request, f'Rol de {user_obj.email} actualizado a {user_obj.get_rol_display()}.')

        elif accion == 'toggle_activo':
            user_id = request.POST.get('user_id')
            user_obj = get_object_or_404(Usuario, id=user_id)
            if user_obj == request.user:
                messages.error(request, 'No puedes desactivar tu propia cuenta en uso.')
            else:
                user_obj.is_active = not user_obj.is_active
                user_obj.save(update_fields=['is_active'])
                estado_txt = 'activada' if user_obj.is_active else 'desactivada'
                _registrar_cambio_cuenta(request, user_obj, f'cuenta {estado_txt}')
                messages.success(request, f'Cuenta {user_obj.email} {estado_txt}.')

        elif accion == 'desbloquear':
            user_id = request.POST.get('user_id')
            user_obj = get_object_or_404(Usuario, id=user_id)
            user_obj.bloqueado_hasta = None
            user_obj.save(update_fields=['bloqueado_hasta'])
            _registrar_cambio_cuenta(request, user_obj, 'sanción removida')
            messages.success(request, f'Sanción removida: {user_obj.email} ahora está desbloqueado.')

        elif accion == 'reset_password':
            user_id = request.POST.get('user_id')
            nueva_clave = request.POST.get('nueva_password', '')
            user_obj = get_object_or_404(Usuario, id=user_id)
            if error_password := _errores_password(nueva_clave, user_obj):
                messages.error(request, error_password)
            else:
                user_obj.set_password(nueva_clave)
                user_obj.save(update_fields=['password'])
                _registrar_cambio_cuenta(request, user_obj, 'contraseña restablecida')
                messages.success(request, f'Contraseña de {user_obj.email} restablecida correctamente.')

        elif accion == 'cambiar_estado_equipo':
            equipo_id = request.POST.get('equipo_id')
            nuevo_estado = request.POST.get('nuevo_estado')
            equipo_obj = get_object_or_404(Equipo, id=equipo_id)
            if nuevo_estado not in Equipo.Estado.values:
                messages.error(request, 'Estado de equipo no válido.')
            elif Equipo.Estado.PRESTADO in (equipo_obj.estado, nuevo_estado):
                messages.error(request, 'El estado "Prestado" solo cambia mediante la entrega y devolución de solicitudes.')
            else:
                estado_antiguo = equipo_obj.get_estado_display()
                antes = auditoria.foto(equipo_obj)
                equipo_obj.estado = nuevo_estado
                equipo_obj.version += 1
                equipo_obj.save()
                auditoria.registrar(equipo_obj, request.user, HistorialEquipo.Accion.ESTADO, antes, 'Panel de administración')
                messages.success(
                    request,
                    f'Estado del equipo "{equipo_obj.nombre}" ({equipo_obj.codigo_inventario}) '
                    f'actualizado exitosamente de {estado_antiguo} a {equipo_obj.get_estado_display()}.'
                )

        return redirect('admin_panel')

    filtro_rol = request.GET.get('rol', '')
    busqueda = request.GET.get('q', '').strip()
    busqueda_equipo = request.GET.get('q_equipo', '').strip()
    filtro_estado_equipo = request.GET.get('estado_equipo', '').strip()

    qs = Usuario.objects.all().order_by('-date_joined')
    if filtro_rol:
        qs = qs.filter(rol=filtro_rol)
    if busqueda:
        qs = qs.filter(Q(email__icontains=busqueda) | Q(first_name__icontains=busqueda) | Q(last_name__icontains=busqueda))

    qs_equipos = Equipo.objects.all().order_by('nombre')
    if busqueda_equipo:
        qs_equipos = qs_equipos.filter(
            Q(codigo_inventario__icontains=busqueda_equipo) |
            Q(nombre__icontains=busqueda_equipo) |
            Q(modelo__icontains=busqueda_equipo)
        )
    if filtro_estado_equipo:
        qs_equipos = qs_equipos.filter(estado=filtro_estado_equipo)

    metricas = {
        **Usuario.objects.aggregate(
            total_usuarios=Count('id'),
            estudiantes=Count('id', filter=Q(rol=Usuario.Rol.ESTUDIANTE)),
            docentes=Count('id', filter=Q(rol=Usuario.Rol.DOCENTE)),
            directores=Count('id', filter=Q(rol=Usuario.Rol.DIRECTOR_CARRERA)),
            encargados=Count('id', filter=Q(rol=Usuario.Rol.ENCARGADO_LABORATORIO)),
            control_calidad=Count('id', filter=Q(rol=Usuario.Rol.CONTROL_CALIDAD)),
            bloqueados=Count('id', filter=Q(bloqueado_hasta__gt=timezone.now())),
            staff=Count('id', filter=Q(is_staff=True)),
        ),
        **Equipo.objects.aggregate(
            equipos_total=Count('id'),
            equipos_disponibles=Count('id', filter=Q(estado=Equipo.Estado.DISPONIBLE)),
            equipos_mantenimiento=Count('id', filter=Q(estado=Equipo.Estado.EN_MANTENIMIENTO)),
            equipos_prestados=Count('id', filter=Q(estado=Equipo.Estado.PRESTADO)),
            equipos_baja=Count('id', filter=Q(estado=Equipo.Estado.FUERA_SERVICIO)),
        ),
    }

    ultimos_movimientos = Movimiento.objects.select_related('solicitud', 'responsable').order_by('-fecha')[:10]

    return render(request, 'inventario/admin_panel.html', {
        'usuarios': Paginator(qs, 25).get_page(request.GET.get('page_usuarios')),
        'equipos_admin': Paginator(qs_equipos, 25).get_page(request.GET.get('page_equipos')),
        'metricas': metricas,
        'roles_choices': Usuario.Rol.choices,
        'estados_equipos_choices': Equipo.Estado.choices,
        'filtro_rol': filtro_rol,
        'busqueda': busqueda,
        'busqueda_equipo': busqueda_equipo,
        'filtro_estado_equipo': filtro_estado_equipo,
        'ultimos_movimientos': ultimos_movimientos,
    })


@csrf_exempt
@require_POST
def tareas_view(request):
    recibido = request.headers.get('Authorization', '').removeprefix('Bearer ')
    if not settings.TAREAS_TOKEN or not hmac.compare_digest(recibido, settings.TAREAS_TOKEN):
        return JsonResponse({'error': 'No autorizado'}, status=401)
    return JsonResponse(tareas.ejecutar())


class CambiarContrasenaView(PasswordChangeView):
    template_name = 'inventario/cambiar_contrasena.html'
    success_url = reverse_lazy('dashboard')

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        _registrar_cambio_cuenta(self.request, self.request.user, 'contraseña cambiada por el titular')
        messages.success(self.request, 'Tu contraseña se actualizó correctamente.')
        return respuesta
