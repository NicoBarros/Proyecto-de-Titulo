from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, Q
from django.shortcuts import render

from ..models import Equipo, Insumo, Solicitud, Usuario


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
