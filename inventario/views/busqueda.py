import time
from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .. import busqueda_semantica, rag
from ..models import BusquedaIA, Equipo

VENTANA_REFORMULACION = timedelta(minutes=5)


def _cupo_ia_disponible(usuario):
    clave = f'ia_consultas:{usuario.pk}:{timezone.now():%Y%m%d%H}'
    cache.add(clave, 0, 3600)
    return cache.incr(clave) <= settings.IA_CONSULTAS_POR_HORA


def _resultado(equipo, disponibles, busqueda):
    return {
        'nombre': equipo.nombre,
        'modelo': equipo.modelo or '',
        'codigo_inventario': equipo.codigo_inventario,
        'estado': equipo.get_estado_display(),
        'disponibles': disponibles,
        'url': f"{reverse('ficha_equipo', args=[equipo.id])}?busqueda={busqueda.id}",
    }


def _agrupar(encontrados, disponibles, busqueda):
    cantidades = Counter(busqueda_semantica.clave_grupo(e) for e in disponibles)
    grupos = {}
    for equipo in encontrados:
        grupos.setdefault(busqueda_semantica.clave_grupo(equipo), equipo)
    return [_resultado(e, cantidades[clave], busqueda) for clave, e in grupos.items()]


def _es_reformulacion(usuario):
    return BusquedaIA.objects.filter(
        usuario=usuario, fecha__gte=timezone.now() - VENTANA_REFORMULACION, equipo_elegido__isnull=True,
    ).exists()


def registrar_eleccion(usuario, busqueda_id, equipo):
    if not str(busqueda_id or '').isdigit():
        return
    BusquedaIA.objects.filter(id=busqueda_id, usuario=usuario, equipo_elegido__isnull=True).update(
        equipo_elegido=equipo, elegida_en=timezone.now(),
    )


@login_required
def busqueda_view(request):
    if request.method == 'GET':
        return render(request, 'inventario/busqueda.html')

    consulta = (request.POST.get('consulta') or '').strip()[:500]
    if not consulta:
        return JsonResponse({'error': 'Falta consulta'}, status=400)
    inicio = time.perf_counter()
    disponibles = list(Equipo.objects.filter(estado=Equipo.Estado.DISPONIBLE))
    contexto, fuente = rag.recuperar(consulta, disponibles)
    busqueda = BusquedaIA.objects.create(
        usuario=request.user, consulta=consulta, fuente=fuente, resultados=len(contexto),
        contexto=[e.id for e in contexto],
        duracion_ms=round((time.perf_counter() - inicio) * 1000),
        reformulacion=_es_reformulacion(request.user),
    )
    return JsonResponse({
        'fuente': fuente,
        'busqueda': busqueda.id,
        'resultados': _agrupar(contexto, disponibles, busqueda),
        'generar': reverse('generar_respuesta', args=[busqueda.id]) if contexto and settings.GEMINI_API_KEY else None,
        'calificar': reverse('calificar_busqueda', args=[busqueda.id]),
    })


def _respuesta_visible(busqueda):
    visible = busqueda.generacion == BusquedaIA.Generacion.GENERADA
    return JsonResponse({
        'respuesta': busqueda.respuesta if visible else '',
        'citas': busqueda.citas if visible else [],
    })


@login_required
@require_POST
def generar_respuesta(request, id):
    busqueda = get_object_or_404(BusquedaIA, id=id, usuario=request.user)
    if busqueda.generacion != BusquedaIA.Generacion.SIN_GENERACION:
        return _respuesta_visible(busqueda)
    if not busqueda.contexto or not settings.GEMINI_API_KEY or not _cupo_ia_disponible(request.user):
        return _respuesta_visible(busqueda)
    disponibles = list(Equipo.objects.filter(estado=Equipo.Estado.DISPONIBLE))
    por_id = {e.id: e for e in Equipo.objects.filter(id__in=busqueda.contexto)}
    contexto = [por_id[i] for i in busqueda.contexto if i in por_id]
    inicio = time.perf_counter()
    generacion = rag.generar(busqueda.consulta, contexto, disponibles)
    busqueda.generacion = generacion.estado
    busqueda.respuesta = generacion.respuesta
    busqueda.citas = generacion.citas
    busqueda.duracion_generacion_ms = round((time.perf_counter() - inicio) * 1000)
    busqueda.save(update_fields=['generacion', 'respuesta', 'citas', 'duracion_generacion_ms'])
    return _respuesta_visible(busqueda)


@login_required
@require_POST
def calificar_busqueda(request, id):
    busqueda = get_object_or_404(BusquedaIA, id=id, usuario=request.user)
    valor = request.POST.get('util')
    if valor not in ('1', '0'):
        return JsonResponse({'error': 'Calificación no válida'}, status=400)
    busqueda.util = valor == '1'
    busqueda.calificada_en = timezone.now()
    busqueda.save(update_fields=['util', 'calificada_en'])
    return JsonResponse({'util': busqueda.util})
