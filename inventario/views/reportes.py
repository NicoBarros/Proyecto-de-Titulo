from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.postgres.aggregates import StringAgg
from django.core.cache import cache
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .. import evaluacion_busqueda
from ..exportar import generar_excel_reportes
from ..kpi import (
    PERIODOS,
    brechas_busqueda,
    calcular_calidad_ia,
    calcular_kpis,
    calcular_kpis_proyecto,
    calcular_sla,
    indicador_evaluacion,
)
from ..models import Equipo, EvaluacionBusqueda, Solicitud, Usuario


def _puede_evaluar(usuario):
    return usuario.rol in Usuario.ROLES_ESCRITURA_INVENTARIO or usuario.is_superuser


def _sin_acceso(request):
    if request.user.rol in Usuario.ROLES_REPORTES or request.user.is_superuser:
        return None
    messages.error(request, 'Acceso denegado: Los estudiantes y docentes no tienen autorización para ver Reportes y KPIs.')
    return redirect('dashboard')


def _datos(request):
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
    kpis = calcular_kpis_proyecto(periodo)
    operativos = [k for k in calcular_kpis(periodo) if k.clave != 'devoluciones_a_tiempo']

    evaluacion = EvaluacionBusqueda.objects.select_related('ejecutada_por').first()
    sla = calcular_sla(periodo)
    calidad_ia = calcular_calidad_ia(periodo)
    return {
        'sla': sla,
        'sla_cumplidos': sum(1 for k in sla if k.cumple),
        'sla_medidos': sum(1 for k in sla if k.cumple is not None),
        'calidad_ia': calidad_ia,
        'calidad_ia_cumplidos': sum(1 for k in calidad_ia if k.cumple),
        'calidad_ia_medidos': sum(1 for k in calidad_ia if k.cumple is not None),
        'brechas': brechas_busqueda(periodo),
        'evaluacion': evaluacion,
        'evaluacion_indicadores': [indicador_evaluacion(evaluacion)],
        'puede_evaluar': _puede_evaluar(request.user),
        'top_equipos': top_equipos, 'vencidos': vencidos, 'sin_movimiento': sin_movimiento, 'dias': dias,
        'unidades_sin_movimiento': sum(g['unidades'] for g in sin_movimiento),
        'kpis': kpis, 'periodo': periodo, 'periodos': PERIODOS,
        'kpis_cumplidos': sum(1 for k in kpis if k.cumple),
        'kpis_medidos': sum(1 for k in kpis if k.cumple is not None),
        'operativos': operativos,
        'operativos_cumplidos': sum(1 for k in operativos if k.cumple),
        'operativos_medidos': sum(1 for k in operativos if k.cumple is not None),
    }


@login_required
def reportes_view(request):
    return _sin_acceso(request) or render(request, 'inventario/reportes.html', _datos(request))


@login_required
def exportar_reportes(request):
    denegado = _sin_acceso(request)
    if denegado:
        return denegado
    response = HttpResponse(
        generar_excel_reportes(_datos(request)),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="reportes_leica_{timezone.localtime().strftime("%Y%m%d")}.xlsx"'
    return response


@login_required
@require_POST
def evaluar_busqueda(request):
    if not _puede_evaluar(request.user):
        messages.error(request, 'No tienes permiso para evaluar la búsqueda.')
        return redirect('reportes')
    if not cache.add(evaluacion_busqueda.CLAVE_EN_CURSO, True, timeout=30 * 60):
        messages.warning(request, 'Ya hay una evaluación en curso.')
        return redirect('reportes')
    try:
        evaluacion = evaluacion_busqueda.evaluar(usuario=request.user)
    finally:
        cache.delete(evaluacion_busqueda.CLAVE_EN_CURSO)
    nivel = messages.success if evaluacion.cumple else messages.warning
    nivel(request, f'Evaluación completada: {evaluacion.aciertos} de {evaluacion.consultas} consultas acertadas.')
    return redirect('/reportes/#evaluacion-busqueda')
