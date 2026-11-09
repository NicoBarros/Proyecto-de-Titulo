import json
import logging
import re
import time
from collections import Counter
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from .. import busqueda_semantica
from ..models import BusquedaIA, Equipo

logger = logging.getLogger(__name__)

MAX_RESULTADOS = 8
VENTANA_REFORMULACION = timedelta(minutes=5)

PROMPT = """Eres un asistente que ayuda a un encargado de laboratorio a encontrar equipos.
Catalogo de equipos disponibles:
{catalogo}

Necesidad del usuario: "{consulta}"

Responde SOLO con un JSON array de los ids de equipo mas relevantes (maximo {maximo}), ordenados del mas al menos relevante. Ejemplo: [3, 1, 7]"""


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


def _buscar_con_gemini(consulta, disponibles):
    from google import genai
    from google.genai.errors import APIError

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    catalogo = '\n'.join(f"- id={e.id}: {e.nombre} ({e.modelo or 's/modelo'}) - {e.especificaciones or ''}" for e in disponibles)
    prompt = PROMPT.format(catalogo=catalogo, consulta=consulta, maximo=MAX_RESULTADOS)
    try:
        respuesta = client.models.generate_content(model=settings.GEMINI_MODELO, contents=prompt)
    except APIError as e:
        if e.code != 503 and '503' not in str(e):
            raise
        respuesta = client.models.generate_content(model=settings.GEMINI_MODELO_RESPALDO, contents=prompt)

    texto = respuesta.text.replace('```json', '').replace('```', '').strip()
    coincidencia = re.search(r'\[[\d,\s]*\]', texto)
    ids = json.loads(coincidencia.group(0) if coincidencia else texto)
    if not isinstance(ids, list):
        return None
    por_id = {e.id: e for e in disponibles}
    return [por_id[i] for i in ids if i in por_id][:MAX_RESULTADOS]


def _buscar_local(consulta, disponibles):
    terminos = consulta.lower().split()
    puntajes = []
    for equipo in disponibles:
        texto = f'{equipo.nombre} {equipo.modelo or ""} {equipo.especificaciones or ""}'.lower()
        puntaje = sum(1 for t in terminos if t in texto)
        if puntaje:
            puntajes.append((puntaje, equipo))
    puntajes.sort(key=lambda par: par[0], reverse=True)
    return [equipo for _, equipo in puntajes[:MAX_RESULTADOS]]


@login_required
def busqueda_view(request):
    if request.method == 'GET':
        return render(request, 'inventario/busqueda.html')

    consulta = request.POST.get('consulta')
    if not consulta:
        return JsonResponse({'error': 'Falta consulta'}, status=400)
    inicio = time.perf_counter()
    disponibles = list(Equipo.objects.filter(estado=Equipo.Estado.DISPONIBLE))

    encontrados, fuente = None, 'palabras_clave_local'
    if settings.BUSQUEDA_SEMANTICA:
        try:
            encontrados = busqueda_semantica.buscar(consulta, disponibles, MAX_RESULTADOS)
            if encontrados:
                fuente = 'semantica_local'
        except Exception as e:
            logger.warning('Falló la búsqueda semántica (%s). Se usa el siguiente método.', e)

    if not encontrados and settings.GEMINI_API_KEY and _cupo_ia_disponible(request.user):
        try:
            encontrados = _buscar_con_gemini(consulta, disponibles)
            if encontrados is not None:
                fuente = 'ia_gemini'
        except Exception as e:
            logger.warning('Falló la IA de Gemini (%s). Cayendo a búsqueda local.', e)

    if not encontrados:
        encontrados = _buscar_local(consulta, disponibles)
    busqueda = BusquedaIA.objects.create(
        usuario=request.user, consulta=consulta[:500], fuente=fuente,
        resultados=len({busqueda_semantica.clave_grupo(e) for e in encontrados}),
        duracion_ms=round((time.perf_counter() - inicio) * 1000),
        reformulacion=_es_reformulacion(request.user),
    )
    return JsonResponse({
        'fuente': fuente, 'busqueda': busqueda.id, 'resultados': _agrupar(encontrados, disponibles, busqueda),
    })
