import json
import logging
import re

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from ..models import Equipo

logger = logging.getLogger(__name__)

MAX_RESULTADOS = 5

PROMPT = """Eres un asistente que ayuda a un encargado de laboratorio a encontrar equipos.
Catalogo de equipos disponibles:
{catalogo}

Necesidad del usuario: "{consulta}"

Responde SOLO con un JSON array de los ids de equipo mas relevantes (maximo {maximo}), ordenados del mas al menos relevante. Ejemplo: [3, 1, 7]"""


def _cupo_ia_disponible(usuario):
    clave = f'ia_consultas:{usuario.pk}:{timezone.now():%Y%m%d%H}'
    cache.add(clave, 0, 3600)
    return cache.incr(clave) <= settings.IA_CONSULTAS_POR_HORA


def _resultado(equipo):
    return {
        'nombre': equipo.nombre,
        'codigo_inventario': equipo.codigo_inventario,
        'estado': equipo.get_estado_display(),
        'url': reverse('ficha_equipo', args=[equipo.id]),
    }


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
    disponibles = list(Equipo.objects.filter(estado=Equipo.Estado.DISPONIBLE))

    encontrados, fuente = None, 'palabras_clave_local'
    if settings.GEMINI_API_KEY and _cupo_ia_disponible(request.user):
        try:
            encontrados = _buscar_con_gemini(consulta, disponibles)
            if encontrados is not None:
                fuente = 'ia_gemini'
        except Exception as e:
            logger.warning('Falló la IA de Gemini (%s). Cayendo a búsqueda local.', e)

    if not encontrados:
        encontrados = _buscar_local(consulta, disponibles)
    return JsonResponse({'fuente': fuente, 'resultados': [_resultado(e) for e in encontrados]})
