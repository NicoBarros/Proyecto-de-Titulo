from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from .. import servicios
from ..decorators import role_required
from ..forms import MantenimientoForm
from ..models import Mantenimiento, Usuario


def _resolver(request):
    accion = request.POST.get('accion_mant') or request.POST.get('decision')
    mant = servicios.resolver_mantenimiento(request.user, request.POST.get('mant_id'), accion)
    equipo = mant.equipo
    if mant.decision == Mantenimiento.Decision.COMPLETADO:
        messages.success(request, f'Reparación completada. "{equipo.nombre}" ({equipo.codigo_inventario}) está disponible.')
    elif mant.decision == Mantenimiento.Decision.DAR_BAJA:
        messages.warning(request, f'El equipo "{equipo.nombre}" fue dado de baja (Fuera de servicio).')
    else:
        messages.info(request, f'El equipo "{equipo.nombre}" quedó en reparación.')


def _diagnosticar(request):
    form = MantenimientoForm(request.POST)
    if not form.is_valid():
        raise ValueError('Revisa los datos del diagnóstico.')
    mant = servicios.diagnosticar(
        request.user, form.cleaned_data['equipo_id'], form.cleaned_data['falla_descrita'], form.cleaned_data['costo_cotizado'],
    )
    mensaje = f'Diagnóstico registrado. Sugerencia: {mant.get_decision_display().upper()}'
    if mant.porcentaje_costo is not None:
        mensaje += f' ({(mant.porcentaje_costo * 100):.1f}% del valor de adquisición).'
    else:
        mensaje += ' (sin valor de adquisición registrado).'
    messages.info(request, mensaje)


@login_required
@role_required(Usuario.Rol.ENCARGADO_LABORATORIO, Usuario.Rol.CONTROL_CALIDAD, Usuario.Rol.DIRECTOR_CARRERA)
def mantenimiento_view(request):
    if request.method == 'POST':
        try:
            if 'mant_id' in request.POST or 'decision' in request.POST or 'accion_mant' in request.POST:
                _resolver(request)
            else:
                _diagnosticar(request)
        except ValueError as e:
            messages.error(request, str(e))
        return redirect('mantenimiento')

    return render(request, 'inventario/mantenimiento.html', {
        'mantenimientos': Mantenimiento.objects.select_related('equipo'),
        'equipos': servicios.equipos_diagnosticables(),
    })
