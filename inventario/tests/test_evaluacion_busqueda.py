import json
import tempfile
from datetime import timedelta
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from openpyxl import load_workbook

from inventario import evaluacion_busqueda, tareas
from inventario.kpi import indicador_evaluacion
from inventario.models import Equipo, EvaluacionBusqueda

from .base import LeicaTestCase

CONSULTAS = [
    {'consulta': 'multímetro para medir voltaje', 'esperado': ['Multímetro']},
    {'consulta': 'osciloscopio digital', 'esperado': ['Osciloscopio']},
    {'consulta': 'impresora 3d', 'esperado': ['Impresora']},
]


class EvaluacionTestCase(LeicaTestCase):

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.crear_equipo('LTV-001', 'Multímetro digital', modelo='Fluke 115')
        self.crear_equipo('LTV-002', 'Osciloscopio digital', modelo='DS1054Z')


class EvaluarTests(EvaluacionTestCase):

    def test_calcula_aciertos_posicion_y_fallos(self):
        evaluacion = evaluacion_busqueda.evaluar(CONSULTAS, self.encargado)
        self.assertEqual((evaluacion.aciertos, evaluacion.consultas), (2, 3))
        self.assertAlmostEqual(evaluacion.porcentaje, 66.67, places=2)
        self.assertFalse(evaluacion.cumple)
        self.assertEqual(evaluacion.metodo, 'palabras_clave_local')
        self.assertEqual(evaluacion.ejecutada_por, self.encargado)
        self.assertEqual(evaluacion.detalle[0]['posicion'], 1)
        self.assertEqual(evaluacion.detalle[0]['obtenidos'], ['Multímetro digital (Fluke 115)'])
        self.assertEqual([f['consulta'] for f in evaluacion.fallos], ['impresora 3d'])

    def test_cumple_desde_el_ochenta_por_ciento(self):
        evaluacion = evaluacion_busqueda.evaluar(CONSULTAS[:2])
        self.assertEqual(evaluacion.porcentaje, 100)
        self.assertTrue(evaluacion.cumple)

    def test_considera_equipos_prestados_pero_no_los_dados_de_baja(self):
        Equipo.objects.filter(codigo_inventario='LTV-001').update(estado=Equipo.Estado.PRESTADO)
        Equipo.objects.filter(codigo_inventario='LTV-002').update(estado=Equipo.Estado.FUERA_SERVICIO)
        evaluacion = evaluacion_busqueda.evaluar(CONSULTAS[:2])
        self.assertEqual([d['posicion'] for d in evaluacion.detalle], [1, None])

    def test_cuenta_solo_los_cinco_primeros_modelos_distintos(self):
        for i in range(6):
            self.crear_equipo(f'SW-{i}', 'Switch', modelo=f'Modelo {i}')
            self.crear_equipo(f'SW-{i}B', 'Switch', modelo=f'Modelo {i}')
        evaluacion = evaluacion_busqueda.evaluar([{'consulta': 'switch', 'esperado': ['Modelo 5']}])
        self.assertLessEqual(len(evaluacion.detalle[0]['obtenidos']), EvaluacionBusqueda.TOP)
        self.assertEqual(len(set(evaluacion.detalle[0]['obtenidos'])), len(evaluacion.detalle[0]['obtenidos']))

    def test_sin_consultas(self):
        evaluacion = evaluacion_busqueda.evaluar([])
        self.assertIsNone(evaluacion.porcentaje)
        self.assertFalse(evaluacion.cumple)

    def test_archivo_de_referencia_tiene_treinta_consultas_validas(self):
        consultas = evaluacion_busqueda.cargar_consultas()
        self.assertEqual(len(consultas), 30)
        self.assertEqual(len({c['consulta'] for c in consultas}), 30)
        self.assertTrue(all(c['consulta'].strip() and c['esperado'] for c in consultas))


@override_settings(EVALUACION_BUSQUEDA_DIAS=30)
class EvaluacionMensualTests(EvaluacionTestCase):

    def test_evalua_cuando_no_hay_ninguna(self):
        self.assertEqual(tareas.ejecutar()['evaluacion_busqueda'], '0/30')
        self.assertIsNone(EvaluacionBusqueda.objects.get().ejecutada_por)

    def test_no_repite_dentro_del_mes(self):
        evaluacion_busqueda.evaluar(CONSULTAS)
        self.assertIsNone(evaluacion_busqueda.evaluacion_mensual())
        self.assertEqual(EvaluacionBusqueda.objects.count(), 1)

    def test_repite_pasado_el_mes(self):
        anterior = evaluacion_busqueda.evaluar(CONSULTAS)
        EvaluacionBusqueda.objects.filter(id=anterior.id).update(fecha=timezone.now() - timedelta(days=31))
        self.assertIsNotNone(evaluacion_busqueda.evaluacion_mensual())
        self.assertEqual(EvaluacionBusqueda.objects.count(), 2)

    @override_settings(EVALUACION_BUSQUEDA_DIAS=0)
    def test_desactivada(self):
        self.assertIsNone(evaluacion_busqueda.evaluacion_mensual())
        self.assertFalse(EvaluacionBusqueda.objects.exists())

    def test_sin_equipos_no_evalua(self):
        Equipo.objects.all().delete()
        self.assertIsNone(evaluacion_busqueda.evaluacion_mensual())

    def test_no_corre_dos_veces_a_la_vez(self):
        cache.add(evaluacion_busqueda.CLAVE_EN_CURSO, True)
        self.assertIsNone(evaluacion_busqueda.evaluacion_mensual())

    def test_error_no_interrumpe_las_tareas(self):
        with patch('inventario.evaluacion_busqueda.evaluar', side_effect=RuntimeError('modelo no disponible')):
            self.assertEqual(evaluacion_busqueda.evaluacion_mensual(), 'error')
        self.assertTrue(cache.add(evaluacion_busqueda.CLAVE_EN_CURSO, True))


class ComandoEvaluarTests(EvaluacionTestCase):

    def ejecutar(self, consultas):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / 'consultas.json'
            ruta.write_text(json.dumps(consultas), encoding='utf-8')
            salida = StringIO()
            call_command('evaluar_busqueda', consultas=str(ruta), stdout=salida)
        return salida.getvalue()

    def test_informa_cada_consulta_y_el_resultado(self):
        salida = self.ejecutar(CONSULTAS)
        self.assertIn('#1  multímetro para medir voltaje', salida)
        self.assertIn('FALLA  impresora 3d  ->  sin resultados', salida)
        self.assertIn('No cumple: 2 de 3 consultas (66.7 %, meta 80 %)', salida)

    def test_cumple(self):
        self.assertIn('Cumple: 2 de 2 consultas', self.ejecutar(CONSULTAS[:2]))


class ReportesEvaluacionTests(EvaluacionTestCase):

    def test_encargado_evalua_desde_reportes(self):
        self.client.force_login(self.encargado)
        r = self.client.post('/reportes/evaluar-busqueda/')
        self.assertRedirects(r, '/reportes/#evaluacion-busqueda', fetch_redirect_response=False)
        self.assertEqual(EvaluacionBusqueda.objects.get().ejecutada_por, self.encargado)

    def test_comite_ve_la_evaluacion_pero_no_puede_ejecutarla(self):
        evaluacion_busqueda.evaluar(CONSULTAS)
        self.client.force_login(self.comite)
        r = self.client.get('/reportes/')
        self.assertContains(r, 'id="evaluacion-busqueda"')
        self.assertContains(r, '2 de 3 consultas en el top 5')
        self.assertContains(r, 'impresora 3d')
        self.assertNotContains(r, '/reportes/evaluar-busqueda/')
        self.client.post('/reportes/evaluar-busqueda/')
        self.assertEqual(EvaluacionBusqueda.objects.count(), 1)

    def test_sin_evaluaciones(self):
        self.client.force_login(self.encargado)
        r = self.client.get('/reportes/')
        self.assertContains(r, 'Sin evaluaciones')
        self.assertContains(r, '/reportes/evaluar-busqueda/')

    def test_solo_por_post(self):
        self.client.force_login(self.encargado)
        self.assertEqual(self.client.get('/reportes/evaluar-busqueda/').status_code, 405)

    def test_evaluacion_en_curso(self):
        cache.add(evaluacion_busqueda.CLAVE_EN_CURSO, True)
        self.client.force_login(self.encargado)
        self.client.post('/reportes/evaluar-busqueda/')
        self.assertFalse(EvaluacionBusqueda.objects.exists())

    def test_exporta_la_hoja_de_evaluacion(self):
        evaluacion_busqueda.evaluar(CONSULTAS)
        self.client.force_login(self.comite)
        libro = load_workbook(BytesIO(self.client.get('/reportes/exportar/').content))
        hoja = libro['Evaluación búsqueda']
        self.assertIn('2 de 3 en el top 5', hoja['A1'].value)
        self.assertEqual(hoja['C7'].value, 'Sin acierto')
        indicadores = [c.value for c in libro['Indicadores']['A']]
        self.assertIn('Precisión de la búsqueda', indicadores)

    def test_indicador_sin_datos(self):
        indicador = indicador_evaluacion(None)
        self.assertIsNone(indicador.cumple)
        self.assertEqual(indicador.texto, 'Sin datos')
