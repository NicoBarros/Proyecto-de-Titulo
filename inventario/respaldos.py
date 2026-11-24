import hashlib
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import CommandError
from django.db import connections
from django.utils import timezone

logger = logging.getLogger(__name__)

PREFIJO = 'leica_'
EXTENSION = '.dump'
CLAVE_EN_CURSO = 'respaldo_automatico_en_curso'
CLAVE_FALLA_AVISADA = 'respaldo_automatico_falla_avisada'


def base_postgres():
    base = settings.DATABASES['default']
    if 'postgresql' not in base['ENGINE']:
        raise CommandError('Los respaldos requieren PostgreSQL: define DATABASE_URL.')
    return base


def descripcion_base():
    base = base_postgres()
    return f"{base['NAME']} en {base.get('HOST') or 'localhost'}"


def entorno_postgres():
    base = base_postgres()
    entorno = os.environ.copy()
    entorno.update({
        'PGHOST': str(base.get('HOST') or 'localhost'),
        'PGPORT': str(base.get('PORT') or 5432),
        'PGUSER': base.get('USER') or '',
        'PGPASSWORD': base.get('PASSWORD') or '',
        'PGDATABASE': base['NAME'],
    })
    sslmode = base.get('OPTIONS', {}).get('sslmode')
    if sslmode:
        entorno['PGSSLMODE'] = sslmode
    return entorno


def ejecutable(nombre):
    ruta = shutil.which(nombre, path=settings.POSTGRES_BIN or None)
    if not ruta:
        raise CommandError(f'No se encontró {nombre}. Instala el cliente de PostgreSQL o define POSTGRES_BIN.')
    return ruta


def ejecutar(nombre, *argumentos):
    resultado = subprocess.run(
        [ejecutable(nombre), *argumentos], env=entorno_postgres(), capture_output=True, text=True,
    )
    if resultado.returncode != 0:
        raise CommandError(f'{nombre} falló: {resultado.stderr.strip()}')
    return resultado.stdout


def sha256(ruta):
    digest = hashlib.sha256()
    with open(ruta, 'rb') as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b''):
            digest.update(bloque)
    return digest.hexdigest()


def huella(ruta):
    return Path(f'{ruta}.sha256')


def contar_tablas(ruta):
    listado = ejecutar('pg_restore', '--list', str(ruta))
    return sum(1 for linea in listado.splitlines() if ' TABLE DATA ' in linea)


def crear_respaldo(directorio):
    directorio = Path(directorio)
    directorio.mkdir(parents=True, exist_ok=True)
    destino = directorio / f'{PREFIJO}{timezone.localtime():%Y%m%d_%H%M%S}{EXTENSION}'
    parcial = destino.with_suffix('.parcial')
    try:
        ejecutar('pg_dump', '--format=custom', '--no-owner', '--no-privileges', f'--file={parcial}')
        parcial.replace(destino)
    finally:
        parcial.unlink(missing_ok=True)
    tablas = contar_tablas(destino)
    digest = sha256(destino)
    huella(destino).write_text(f'{digest}  {destino.name}\n', encoding='utf-8')
    return destino, tablas, digest


def aplicar_retencion(directorio, conservar):
    if conservar <= 0:
        return []
    respaldos = sorted(Path(directorio).glob(f'{PREFIJO}*{EXTENSION}'), reverse=True)
    eliminados = respaldos[conservar:]
    for respaldo in eliminados:
        respaldo.unlink()
        huella(respaldo).unlink(missing_ok=True)
    return eliminados


def ultimo_respaldo(directorio):
    respaldos = list(Path(directorio).glob(f'{PREFIJO}*{EXTENSION}'))
    return max(respaldos, key=lambda p: p.stat().st_mtime) if respaldos else None


def respaldo_vigente(directorio, horas):
    ultimo = ultimo_respaldo(directorio)
    return ultimo is not None and time.time() - ultimo.stat().st_mtime < horas * 3600


def respaldo_automatico():
    if not settings.RESPALDO_AUTOMATICO:
        return None
    directorio = settings.RESPALDOS_DIR
    if respaldo_vigente(directorio, settings.RESPALDO_HORAS):
        return None
    if not cache.add(CLAVE_EN_CURSO, True, timeout=30 * 60):
        return None
    from . import notificaciones
    try:
        destino, tablas, digest = crear_respaldo(directorio)
        aplicar_retencion(directorio, settings.RESPALDO_CONSERVAR)
    except Exception as error:
        logger.exception('No se pudo generar el respaldo automático')
        if cache.add(CLAVE_FALLA_AVISADA, True, timeout=settings.RESPALDO_HORAS * 3600):
            notificaciones.enviar_falla_respaldo(error)
        return 'error'
    finally:
        cache.delete(CLAVE_EN_CURSO)
    cache.delete(CLAVE_FALLA_AVISADA)
    logger.info('Respaldo automático %s (%s tablas, SHA-256 %s)', destino.name, tablas, digest)
    return destino.name


def verificar_integridad(ruta):
    archivo_huella = huella(ruta)
    if not archivo_huella.exists():
        return False
    esperado = archivo_huella.read_text(encoding='utf-8').split()[0]
    if sha256(ruta) != esperado:
        raise CommandError('El respaldo está dañado: su SHA-256 no coincide con el registrado.')
    return True


def restaurar_respaldo(ruta):
    nombre_base = base_postgres()['NAME']
    connections.close_all()
    ejecutar(
        'pg_restore', '--clean', '--if-exists', '--no-owner', '--no-privileges',
        '--single-transaction', '--exit-on-error', f'--dbname={nombre_base}', str(ruta),
    )
