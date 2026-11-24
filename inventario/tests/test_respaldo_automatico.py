import os
import time
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import override_settings

from inventario import respaldos, tareas

from .test_respaldos import RespaldosTestCase


class RespaldoAutomaticoTests(RespaldosTestCase):

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        ajustes = override_settings(
            RESPALDO_AUTOMATICO=True, RESPALDOS_DIR=str(self.directorio), RESPALDO_HORAS=24, RESPALDO_CONSERVAR=3,
        )
        ajustes.enable()
        self.addCleanup(ajustes.disable)
        self.admin = self.crear_usuario('admin', 'encargado_laboratorio', is_superuser=True, is_staff=True)

    def respaldos_en_disco(self):
        return sorted(p.name for p in self.directorio.glob('leica_*.dump'))

    def respaldo_previo(self, nombre, horas_atras):
        ruta = self.directorio / nombre
        ruta.write_bytes(b'PGDMP')
        momento = time.time() - horas_atras * 3600
        os.utime(ruta, (momento, momento))
        return ruta

    def ejecutar(self, falla=None):
        with self.simular(falla):
            return tareas.ejecutar()['respaldo']

    def test_genera_el_respaldo_cuando_no_hay_ninguno(self):
        nombre = self.ejecutar()
        self.assertEqual(self.respaldos_en_disco(), [nombre])
        self.assertTrue((self.directorio / f'{nombre}.sha256').exists())

    def test_no_repite_dentro_del_mismo_dia(self):
        self.respaldo_previo('leica_20261109_080000.dump', horas_atras=5)
        self.assertIsNone(self.ejecutar())
        self.assertEqual(self.llamadas, [])

    def test_respalda_de_nuevo_pasado_el_plazo_y_aplica_retencion(self):
        for i, horas in enumerate((96, 72, 48, 25)):
            self.respaldo_previo(f'leica_2026110{i}_080000.dump', horas_atras=horas)
        nombre = self.ejecutar()
        self.assertEqual(self.respaldos_en_disco(), ['leica_20261102_080000.dump', 'leica_20261103_080000.dump', nombre])

    @override_settings(RESPALDO_AUTOMATICO=False)
    def test_desactivado_no_hace_nada(self):
        self.assertIsNone(self.ejecutar())
        self.assertEqual(self.llamadas, [])

    def test_no_corre_dos_veces_a_la_vez(self):
        cache.add(respaldos.CLAVE_EN_CURSO, True)
        self.assertIsNone(self.ejecutar())
        self.assertEqual(self.llamadas, [])

    def test_falla_avisa_una_sola_vez_y_reintenta(self):
        self.assertEqual(self.ejecutar(falla='pg_dump'), 'error')
        self.assertEqual(self.ejecutar(falla='pg_dump'), 'error')
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['admin@inacapmail.cl'])
        self.assertIn('conexión rechazada', mail.outbox[0].body)
        self.assertEqual(self.respaldos_en_disco(), [])
        self.assertIsNotNone(self.ejecutar())
        self.assertFalse(cache.get(respaldos.CLAVE_FALLA_AVISADA))

    def test_falla_sin_administradores_con_correo(self):
        self.admin.email = ''
        self.admin.save()
        self.assertEqual(self.ejecutar(falla='pg_dump'), 'error')
        self.assertEqual(mail.outbox, [])

    def test_si_el_correo_falla_no_interrumpe_las_tareas(self):
        with patch('inventario.notificaciones.send_mail', side_effect=OSError('smtp caído')):
            self.assertEqual(self.ejecutar(falla='pg_dump'), 'error')
