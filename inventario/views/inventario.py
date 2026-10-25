import io

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F, ProtectedError, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .. import auditoria, servicios
from ..decorators import role_required
from ..exportar import generar_excel_inventario, generar_plantilla_importacion
from ..forms import EquipoForm, InsumoForm
from ..importar import importar_inventario
from ..models import Equipo, HistorialEquipo, Insumo, Migracion, Solicitud, SolicitudItem, Usuario

EDITORES = (Usuario.Rol.ENCARGADO_LABORATORIO, Usuario.Rol.CONTROL_CALIDAD)


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
        context['ubicaciones'] = sorted(set(ubicaciones))

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
        context['categorias'] = sorted(set(categorias))

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
@role_required(*EDITORES)
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
@role_required(*EDITORES)
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
@role_required(*EDITORES)
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
@role_required(*EDITORES)
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
@role_required(*EDITORES)
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
@role_required(*EDITORES)
def editar_insumo(request, id):
    insumo = get_object_or_404(Insumo, id=id)
    if request.method == 'POST':
        with transaction.atomic():
            insumo = get_object_or_404(Insumo.objects.select_for_update(), id=id)
            entregadas = servicios.unidades_entregadas(insumo)
            form = InsumoForm(request.POST, instance=insumo)
            if form.is_valid():
                try:
                    servicios.aplicar_total_insumo(form.save(commit=False), entregadas)
                except ValueError as e:
                    form.add_error('cantidad_total', str(e))
                else:
                    messages.success(request, 'Insumo actualizado exitosamente.')
                    return redirect('/inventario/?tab=insumos')
    else:
        form = InsumoForm(instance=insumo)
    return render(request, 'inventario/editar_insumo.html', {'form': form, 'insumo': insumo})


@login_required
@role_required(*EDITORES)
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
@role_required(*EDITORES)
def plantilla_importacion(request):
    response = HttpResponse(
        generar_plantilla_importacion(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="plantilla_inventario_leica.xlsx"'
    return response


@login_required
@role_required(*EDITORES)
def exportar_inventario(request):
    """Genera y descarga un Excel del inventario (Equipos e Insumos) automáticamente."""
    response = HttpResponse(
        generar_excel_inventario(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="inventario_leica_{timezone.localtime().strftime("%Y%m%d")}.xlsx"'
    return response
