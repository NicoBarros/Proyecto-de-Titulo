from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .. import servicios
from ..models import Equipo, Insumo, Solicitud, Usuario


def _parse_fecha(valor):
    fecha = parse_datetime(valor or '')
    if fecha is None:
        return None
    if timezone.is_naive(fecha):
        fecha = timezone.make_aware(fecha)
    return fecha


def _crear(request):
    try:
        servicios.crear_solicitud(
            request.user,
            items=request.POST.getlist('item[]'),
            cantidades=request.POST.getlist('cantidad[]'),
            inicio=_parse_fecha(request.POST.get('horario_inicio')),
            fin=_parse_fecha(request.POST.get('horario_fin')),
            lugar_uso=request.POST.get('lugar_uso'),
            justificacion=request.POST.get('justificacion'),
            representado_id=request.POST.get('en_representacion_de'),
        )
    except ValueError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, 'Solicitud (Kit) creada correctamente.')


def _accion(request, puede_aprobar):
    accion = request.POST.get('accion')
    if not puede_aprobar and accion != 'cancelar':
        messages.error(request, 'No tienes permiso para aprobar solicitudes.')
        return
    try:
        servicios.aplicar_accion_solicitud(request.user, request.POST.get('solicitud_id'), accion, request.POST)
    except ValueError as e:
        messages.error(request, str(e))
    else:
        messages.success(request, f'Solicitud {servicios.PARTICIPIOS_ACCION[accion]} correctamente.')


@login_required
def solicitudes_view(request):
    Solicitud.marcar_atrasadas()
    puede_aprobar = request.user.rol in Usuario.ROLES_APROBADORES or request.user.is_superuser
    puede_representar = request.user.rol in Usuario.ROLES_REPRESENTANTES

    if request.method == 'POST':
        if 'item[]' in request.POST:
            _crear(request)
        elif 'accion' in request.POST:
            _accion(request, puede_aprobar)
        return redirect('solicitudes')

    solicitudes = (
        Solicitud.objects.all()
        .select_related('solicitante', 'en_representacion_de')
        .prefetch_related('items', 'items__equipo', 'items__insumo')
    )
    if not puede_aprobar:
        solicitudes = solicitudes.filter(Q(solicitante=request.user) | Q(en_representacion_de=request.user))
    estudiantes = []
    if puede_representar:
        estudiantes = Usuario.objects.filter(rol=Usuario.Rol.ESTUDIANTE, is_active=True).order_by('first_name', 'email')

    return render(request, 'inventario/solicitudes.html', {
        'solicitudes': Paginator(solicitudes, 20).get_page(request.GET.get('page')),
        'equipos': Equipo.objects.filter(estado=Equipo.Estado.DISPONIBLE),
        'insumos': Insumo.objects.all(),
        'puede_aprobar': puede_aprobar,
        'equipo_preseleccionado': request.GET.get('equipo', ''),
        'estudiantes': estudiantes,
        'ahora': timezone.now(),
    })
