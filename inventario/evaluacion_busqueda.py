import json
import logging
import time
from collections import Counter
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from . import rag
from .models import Equipo, EvaluacionBusqueda

logger = logging.getLogger(__name__)

RUTA_CONSULTAS = Path(__file__).resolve().parent / 'datos' / 'consultas_referencia.json'
CLAVE_EN_CURSO = 'evaluacion_busqueda_en_curso'


def cargar_consultas(ruta=None):
    return json.loads(Path(ruta or RUTA_CONSULTAS).read_text(encoding='utf-8'))


def _texto_grupo(nombre, modelo):
    return f'{nombre} ({modelo})' if modelo else nombre


def _posicion(grupos, esperados):
    esperados = [e.lower() for e in esperados]
    for i, (nombre, modelo) in enumerate(grupos, start=1):
        texto = f'{nombre} {modelo}'.lower()
        if any(e in texto for e in esperados):
            return i
    return None


def evaluar(consultas=None, usuario=None):
    consultas = cargar_consultas() if consultas is None else consultas
    catalogo = list(Equipo.objects.exclude(estado=Equipo.Estado.FUERA_SERVICIO))
    inicio = time.perf_counter()
    detalle, fuentes = [], Counter()
    for item in consultas:
        encontrados, fuente = rag.recuperar(item['consulta'], catalogo)
        fuentes[fuente] += 1
        grupos = list(dict.fromkeys((e.nombre, e.modelo or '') for e in encontrados))[:EvaluacionBusqueda.TOP]
        detalle.append({
            'consulta': item['consulta'],
            'esperado': item['esperado'],
            'obtenidos': [_texto_grupo(n, m) for n, m in grupos],
            'posicion': _posicion(grupos, item['esperado']),
            'fuente': fuente,
        })
    return EvaluacionBusqueda.objects.create(
        ejecutada_por=usuario,
        metodo=fuentes.most_common(1)[0][0] if fuentes else '',
        consultas=len(detalle),
        aciertos=sum(1 for d in detalle if d['posicion']),
        duracion_ms=round((time.perf_counter() - inicio) * 1000),
        detalle=detalle,
    )


def evaluacion_mensual():
    dias = settings.EVALUACION_BUSQUEDA_DIAS
    if dias <= 0 or not Equipo.objects.exists():
        return None
    if EvaluacionBusqueda.objects.filter(fecha__gte=timezone.now() - timedelta(days=dias)).exists():
        return None
    if not cache.add(CLAVE_EN_CURSO, True, timeout=30 * 60):
        return None
    try:
        evaluacion = evaluar()
    except Exception:
        logger.exception('No se pudo ejecutar la evaluación de la búsqueda')
        return 'error'
    finally:
        cache.delete(CLAVE_EN_CURSO)
    return f'{evaluacion.aciertos}/{evaluacion.consultas}'
