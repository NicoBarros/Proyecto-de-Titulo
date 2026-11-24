import hashlib
import logging
import re
import threading
import time
from itertools import zip_longest

import numpy as np
from django.conf import settings

from .models import VectorEquipo

logger = logging.getLogger(__name__)

MODELO = 'google/embeddinggemma-300m'
PREFIJO_CONSULTA = 'task: search result | query: '
PREFIJO_DOCUMENTO = 'title: none | text: '
SIMILITUD_MINIMA = 0.15
MARGEN = 0.1
MARGEN_POR_PARTE = 0.05
RESULTADOS_POR_PARTE = 2
SEPARADORES = re.compile(r',|;|\b(?:y|e|con|además|junto a|conectad[oa]s? a)\b', re.IGNORECASE)
ESPERA_TRAS_FALLO = 600

_modelo = None
_reintentar_desde = 0.0
_candado = threading.Lock()


class ModeloNoDisponible(Exception):
    pass


def _cargar_modelo():
    global _modelo, _reintentar_desde
    with _candado:
        if _modelo is not None:
            return _modelo
        if time.monotonic() < _reintentar_desde:
            raise ModeloNoDisponible('El modelo de búsqueda falló recientemente.')
        try:
            from fastembed import TextEmbedding
            _modelo = TextEmbedding(MODELO, cache_dir=settings.MODELOS_DIR)
        except Exception as e:
            _reintentar_desde = time.monotonic() + ESPERA_TRAS_FALLO
            raise ModeloNoDisponible(str(e)) from e
        return _modelo


def _normalizar(vectores):
    vectores = np.asarray(vectores, dtype=np.float32)
    return vectores / np.linalg.norm(vectores, axis=-1, keepdims=True)


def vectorizar_documentos(textos):
    return _normalizar(list(_cargar_modelo().embed([PREFIJO_DOCUMENTO + t for t in textos])))


def vectorizar_consulta(texto):
    return _normalizar(next(iter(_cargar_modelo().embed([PREFIJO_CONSULTA + texto]))))


def texto_equipo(equipo):
    return ' '.join(filter(None, [equipo.nombre, equipo.modelo, equipo.especificaciones]))


def _huella(texto):
    return hashlib.sha256(f'{MODELO}\n{texto}'.encode()).hexdigest()


def indexar(equipos):
    textos = {e.id: texto_equipo(e) for e in equipos}
    vectores = {
        v.equipo_id: np.frombuffer(v.vector, dtype=np.float32)
        for v in VectorEquipo.objects.filter(equipo_id__in=textos)
        if v.huella == _huella(textos[v.equipo_id])
    }
    pendientes = [i for i in textos if i not in vectores]
    if pendientes:
        nuevos = vectorizar_documentos([textos[i] for i in pendientes])
        VectorEquipo.objects.bulk_create(
            [
                VectorEquipo(equipo_id=i, huella=_huella(textos[i]), vector=v.tobytes())
                for i, v in zip(pendientes, nuevos, strict=True)
            ],
            update_conflicts=True, unique_fields=['equipo'], update_fields=['huella', 'vector', 'actualizado'],
        )
        vectores.update(zip(pendientes, nuevos, strict=True))
    return vectores, len(pendientes)


def clave_grupo(equipo):
    return equipo.nombre, equipo.modelo or ''


def partes_consulta(consulta):
    partes = [p.strip() for p in SEPARADORES.split(consulta) if len(p.strip()) > 2]
    return partes or [consulta]


def _mejores(similitudes, margen, maximo):
    corte = max(SIMILITUD_MINIMA, float(similitudes.max()) - margen)
    return [int(i) for i in np.argsort(-similitudes)[:maximo] if similitudes[i] >= corte]


def buscar(consulta, disponibles, maximo):
    grupos = {}
    for equipo in disponibles:
        grupos.setdefault(clave_grupo(equipo), equipo)
    representantes = list(grupos.values())
    if not representantes:
        return []
    vectores, _ = indexar(representantes)
    matriz = np.stack([vectores[e.id] for e in representantes])
    partes = partes_consulta(consulta)
    if len(partes) == 1:
        elegidos = _mejores(matriz @ vectorizar_consulta(consulta), MARGEN, maximo)
    else:
        por_parte = [_mejores(matriz @ vectorizar_consulta(p), MARGEN_POR_PARTE, RESULTADOS_POR_PARTE) for p in partes]
        elegidos = list(dict.fromkeys(i for ronda in zip_longest(*por_parte) for i in ronda if i is not None))[:maximo]
    return [representantes[i] for i in elegidos]
