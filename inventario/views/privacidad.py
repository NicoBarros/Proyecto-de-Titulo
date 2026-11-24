import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from .. import privacidad
from ..models import SolicitudDerecho


def aviso_privacidad(request):
    return render(request, 'inventario/privacidad.html', {
        'retencion_busquedas': settings.RETENCION_BUSQUEDAS_DIAS,
        'retencion_eventos': settings.RETENCION_EVENTOS_DIAS,
        'plazo_derechos': settings.PLAZO_DERECHOS_DIAS,
        'contacto': settings.PRIVACIDAD_CONTACTO,
    })


@login_required
def mis_datos(request):
    if request.method == 'POST':
        try:
            privacidad.crear_solicitud_derecho(request.user, request.POST.get('tipo'), request.POST.get('detalle'))
        except ValueError as e:
            messages.error(request, str(e))
        else:
            messages.success(request, 'Recibimos tu solicitud. Te responderemos por correo.')
        return redirect('mis_datos')
    return render(request, 'inventario/mis_datos.html', {
        'resumen': privacidad.resumen(request.user),
        'derechos': request.user.solicitudes_derechos.all(),
        'tipos_derecho': SolicitudDerecho.Tipo.choices,
        'plazo_derechos': settings.PLAZO_DERECHOS_DIAS,
    })


@login_required
def descargar_mis_datos(request):
    contenido = json.dumps(privacidad.datos_personales(request.user), ensure_ascii=False, indent=2)
    respuesta = HttpResponse(contenido, content_type='application/json; charset=utf-8')
    nombre = f'mis_datos_leica_{timezone.localtime():%Y%m%d}.json'
    respuesta['Content-Disposition'] = f'attachment; filename="{nombre}"'
    return respuesta
