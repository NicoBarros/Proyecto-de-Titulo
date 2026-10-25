import subprocess
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError

from inventario import respaldos

from .base import LeicaTestCase

LISTADO = '\n'.join([
    '; Archive created at 2026-10-21',
    '215; 1259 16390 TABLE public inventario_equipo leica',
    '3401; 0 16390 TABLE DATA public inventario_equipo leica',
    '3402; 0 16400 TABLE DATA public inventario_usuario leica',
])


def pg_falso(llamadas, falla=None):
    def run(argumentos, env, **kwargs):
        llamadas.append((argumentos, env))
        programa = Path(argumentos[0]).stem
        if programa == falla:
            return subprocess.CompletedProcess(argumentos, 1, '', 'conexión rechazada')
        if programa == 'pg_dump':
            destino = next(a.split('=', 1)[1] for a in argumentos if a.startswith('--file='))
            Path(destino).write_bytes(b'PGDMP contenido')
        salida = LISTADO if '--list' in argumentos else ''
        return subprocess.CompletedProcess(argumentos, 0, salida, '')
    return run


class RespaldosTestCase(LeicaTestCase):

    def setUp(self):
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.directorio = Path(temporal.name)
        self.llamadas = []
        which = patch('inventario.respaldos.shutil.which', side_effect=lambda nombre, path=None: f'/usr/bin/{nombre}')
        which.start()
        self.addCleanup(which.stop)

    def simular(self, falla=None):
        return patch('inventario.respaldos.subprocess.run', side_effect=pg_falso(self.llamadas, falla))


class RespaldarTests(RespaldosTestCase):

    def respaldar(self, *args):
        salida = StringIO()
        with self.simular():
            call_command('respaldar', '--directorio', str(self.directorio), *args, stdout=salida)
        return salida.getvalue()

    def test_genera_respaldo_con_huella_sha256(self):
        salida = self.respaldar()
        respaldo, = self.directorio.glob('leica_*.dump')
        huella = Path(f'{respaldo}.sha256').read_text(encoding='utf-8')
        self.assertEqual(huella.split()[0], respaldos.sha256(respaldo))
        self.assertIn('Tablas:  2', salida)
        self.assertNotIn('.parcial', ' '.join(p.name for p in self.directorio.iterdir()))

    def test_usa_formato_comprimido_y_no_expone_la_clave(self):
        self.respaldar()
        argumentos, entorno = self.llamadas[0]
        self.assertIn('--format=custom', argumentos)
        self.assertEqual(entorno['PGPASSWORD'], settings.DATABASES['default']['PASSWORD'] or '')
        self.assertEqual(entorno['PGDATABASE'], settings.DATABASES['default']['NAME'])
        if settings.DATABASES['default']['PASSWORD']:
            self.assertNotIn(settings.DATABASES['default']['PASSWORD'], ' '.join(argumentos))

    def test_conserva_solo_los_mas_recientes(self):
        for fecha in ('20260101_000000', '20260102_000000', '20260103_000000'):
            (self.directorio / f'leica_{fecha}.dump').write_bytes(b'x')
            (self.directorio / f'leica_{fecha}.dump.sha256').write_text('x', encoding='utf-8')
        salida = self.respaldar('--conservar', '2')
        restantes = sorted(p.name for p in self.directorio.glob('leica_*.dump'))
        self.assertEqual(len(restantes), 2)
        self.assertIn('leica_20260103_000000.dump', restantes)
        self.assertFalse((self.directorio / 'leica_20260101_000000.dump.sha256').exists())
        self.assertIn('Respaldo antiguo eliminado: leica_20260102_000000.dump', salida)

    def test_conservar_cero_no_elimina_nada(self):
        (self.directorio / 'leica_20200101_000000.dump').write_bytes(b'x')
        self.respaldar('--conservar', '0')
        self.assertEqual(len(list(self.directorio.glob('leica_*.dump'))), 2)

    def test_falla_de_pg_dump_no_deja_archivos(self):
        with self.simular(falla='pg_dump'), self.assertRaisesMessage(CommandError, 'conexión rechazada'):
            call_command('respaldar', '--directorio', str(self.directorio), stdout=StringIO())
        self.assertEqual(list(self.directorio.iterdir()), [])

    def test_sin_cliente_postgres_informa_el_error(self):
        with patch('inventario.respaldos.shutil.which', return_value=None), \
                self.assertRaisesMessage(CommandError, 'POSTGRES_BIN'):
            call_command('respaldar', '--directorio', str(self.directorio), stdout=StringIO())

    def test_requiere_postgresql(self):
        with patch.dict(settings.DATABASES['default'], ENGINE='django.db.backends.sqlite3'), \
                self.assertRaisesMessage(CommandError, 'PostgreSQL'):
            call_command('respaldar', '--directorio', str(self.directorio), stdout=StringIO())

    def test_propaga_sslmode(self):
        opciones = {**settings.DATABASES['default'].get('OPTIONS', {}), 'sslmode': 'require'}
        with patch.dict(settings.DATABASES['default'], OPTIONS=opciones):
            self.assertEqual(respaldos.entorno_postgres()['PGSSLMODE'], 'require')


class RestaurarTests(RespaldosTestCase):

    def setUp(self):
        super().setUp()
        self.respaldo = self.directorio / 'leica_20261021_120000.dump'
        self.respaldo.write_bytes(b'PGDMP contenido')
        Path(f'{self.respaldo}.sha256').write_text(f'{respaldos.sha256(self.respaldo)}  x\n', encoding='utf-8')
        self.crear_equipo()

    def restaurar(self, *args):
        salida = StringIO()
        with self.simular(), patch('inventario.respaldos.connections.close_all'):
            call_command('restaurar', str(self.respaldo), *args, stdout=salida)
        return salida.getvalue()

    def test_restaura_en_una_transaccion_y_resume_los_datos(self):
        salida = self.restaurar('--noinput')
        argumentos, _ = self.llamadas[0]
        self.assertIn('--single-transaction', argumentos)
        self.assertIn('--clean', argumentos)
        self.assertIn(f"--dbname={settings.DATABASES['default']['NAME']}", argumentos)
        self.assertIn('Integridad verificada', salida)
        self.assertIn('Equipos: 1', salida)

    def test_rechaza_respaldo_alterado(self):
        self.respaldo.write_bytes(b'PGDMP alterado')
        with self.assertRaisesMessage(CommandError, 'dañado'):
            self.restaurar('--noinput')
        self.assertEqual(self.llamadas, [])

    def test_sin_huella_advierte_y_restaura(self):
        Path(f'{self.respaldo}.sha256').unlink()
        salida = self.restaurar('--noinput')
        self.assertIn('no se verificó su integridad', salida)
        self.assertEqual(len(self.llamadas), 1)

    def test_pide_confirmacion_con_el_nombre_de_la_base(self):
        with patch('builtins.input', return_value='otra'), self.assertRaisesMessage(CommandError, 'cancelada'):
            self.restaurar()
        self.assertEqual(self.llamadas, [])
        with patch('builtins.input', return_value=settings.DATABASES['default']['NAME']):
            self.restaurar()
        self.assertEqual(len(self.llamadas), 1)

    def test_archivo_inexistente(self):
        with self.assertRaisesMessage(CommandError, 'No existe'):
            call_command('restaurar', str(self.directorio / 'nada.dump'), '--noinput', stdout=StringIO())
