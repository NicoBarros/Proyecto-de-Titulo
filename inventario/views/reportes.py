from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.postgres.aggregates import StringAgg
from django.db.models import Count
from django.shortcuts import redirect, render
from django.utils import timezone

from ..kpi import PERIODOS, calcular_kpis
from ..models import Equipo, Solicitud, Usuario


@login_required
def reportes_view(request):
    """RF-13: Reportes (Restringido para Estudiantes y Docentes)."""
    if request.user.rol not in Usuario.ROLES_REPORTES and not request.user.is_superuser:
        messages.error(request, 'Acceso denegado: Los estudiantes y docentes no tienen autorización para ver Reportes y KPIs.')
        return redirect('dashboard')

    top_equipos = (
        Equipo.objects.values('nombre', 'modelo').annotate(veces=Count('solicituditem'))
        .filter(veces__gt=0).order_by('-veces', 'nombre')[:10]
    )
    Solicitud.marcar_atrasadas()
    vencidos = list(
        Solicitud.objects.filter(estado=Solicitud.EstadoSolicitud.ATRASADA)
        .select_related('solicitante', 'en_representacion_de').order_by('horario_fin')
    )

    dias_str = request.GET.get('dias', '90')
    dias = min(int(dias_str), 3650) if dias_str.isdigit() else 90
    fecha_limite = timezone.now() - timedelta(days=dias)
    sin_movimiento = list(
        Equipo.objects.exclude(solicituditem__solicitud__created_at__gte=fecha_limite)
        .exclude(estado=Equipo.Estado.FUERA_SERVICIO)
        .values('nombre', 'modelo')
        .annotate(unidades=Count('id'), ubicaciones=StringAgg('ubicacion', ' · ', distinct=True, default=''))
        .order_by('-unidades', 'nombre')
    )

    periodo_str = request.GET.get('periodo', '30')
    periodo = int(periodo_str) if periodo_str.isdigit() and int(periodo_str) in PERIODOS else 30
    kpis = calcular_kpis(periodo)

    return render(request, 'inventario/reportes.html', {
        'top_equipos': top_equipos, 'vencidos': vencidos, 'sin_movimiento': sin_movimiento, 'dias': dias,
        'unidades_sin_movimiento': sum(g['unidades'] for g in sin_movimiento),
        'kpis': kpis, 'periodo': periodo, 'periodos': PERIODOS,
        'kpis_cumplidos': sum(1 for k in kpis if k.cumple),
        'kpis_medidos': sum(1 for k in kpis if k.cumple is not None),
    })
