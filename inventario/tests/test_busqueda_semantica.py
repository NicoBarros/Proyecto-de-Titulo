from io import StringIO
from unittest.mock import patch

import numpy as np
from django.core.management import call_command
from django.test import override_settings

from inventario import busqueda_semantica, tareas
from inventario.models import Equipo, VectorEquipo

from .base import LeicaTestCase

EJES = ['osciloscopio', 'multimetro', 'router']


def vector(texto):
    v = np.array([1.0 if eje in texto.lower() else 0.0 for eje in EJES] + [0.05], dtype=np.float32)
    return v / np.linalg.norm(v)


def documentos_falsos(textos):
    return np.stack([vector(t) for t in textos])


@override_settings(BUSQUEDA_SEMANTICA=True)
class BusquedaSemanticaTests(LeicaTestCase):

    def setUp(self):
        self.client.force_login(self.estudiante)
        self.osc = self.crear_equipo('S-1', 'Osciloscopio', especificaciones='50 MHz')
        self.mul = self.crear_equipo('S-2', 'Multimetro digital')
        self.prestado = self.crear_equipo('S-3', 'Osciloscopio portatil', estado=Equipo.Estado.PRESTADO)
        documentos = patch('inventario.busqueda_semantica.vectorizar_documentos', side_effect=documentos_falsos)
        consulta = patch('inventario.busqueda_semantica.vectorizar_consulta', side_effect=vector)
        self.documentos = documentos.start()
        self.consulta = consulta.start()
        self.addCleanup(documentos.stop)
        self.addCleanup(consulta.stop)

    def buscar(self, consulta):
        return self.client.post('/busqueda/', {'consulta': consulta}).json()

    def codigos(self, data):
        return [r['codigo_inventario'] for r in data['resultados']]

    def test_usa_busqueda_semantica(self):
        data = self.buscar('ver una señal en el osciloscopio')
        self.assertEqual(data['fuente'], 'semantica_local')
        self.assertEqual(self.codigos(data), ['S-1'])

    def test_no_incluye_equipos_no_disponibles(self):
        self.assertNotIn('S-3', self.codigos(self.buscar('osciloscopio')))

    def test_guarda_vectores_y_no_los_recalcula(self):
        self.buscar('osciloscopio')
        self.buscar('multimetro')
        self.assertEqual(self.documentos.call_count, 1)
        self.assertEqual(VectorEquipo.objects.count(), 2)

    def test_recalcula_el_vector_si_cambia_el_equipo(self):
        self.buscar('osciloscopio')
        self.mul.nombre = 'Router Cisco'
        self.mul.save()
        self.assertEqual(self.codigos(self.buscar('router')), ['S-2'])
        self.assertEqual(self.documentos.call_args.args[0], ['Router Cisco'])

    def test_descarta_resultados_lejanos_al_mejor(self):
        self.crear_equipo('S-4', 'Kit osciloscopio y multimetro')
        self.assertEqual(self.codigos(self.buscar('osciloscopio y multimetro')), ['S-4'])

    def test_sin_coincidencias_usa_palabras_clave(self):
        data = self.buscar('silla')
        self.assertEqual(data['fuente'], 'palabras_clave_local')
        self.assertEqual(data['resultados'], [])

    @override_settings(GEMINI_API_KEY='clave-falsa')
    @patch('google.genai.Client')
    def test_sin_coincidencias_consulta_a_gemini(self, client_cls):
        client_cls.return_value.models.generate_content.return_value.text = f'[{self.mul.id}]'
        data = self.buscar('silla')
        self.assertEqual(data['fuente'], 'ia_gemini')
        self.assertEqual(self.codigos(data), ['S-2'])

    def test_si_el_modelo_falla_usa_palabras_clave(self):
        self.consulta.side_effect = busqueda_semantica.ModeloNoDisponible('sin modelo')
        data = self.buscar('multimetro')
        self.assertEqual(data['fuente'], 'palabras_clave_local')
        self.assertEqual(self.codigos(data), ['S-2'])

    @override_settings(BUSQUEDA_SEMANTICA=False)
    def test_desactivada_no_carga_el_modelo(self):
        self.assertEqual(self.buscar('multimetro')['fuente'], 'palabras_clave_local')
        self.consulta.assert_not_called()

    def test_tareas_actualizan_el_indice(self):
        self.assertEqual(tareas.ejecutar()['vectores_actualizados'], 3)
        self.assertEqual(tareas.ejecutar()['vectores_actualizados'], 0)

    def test_tareas_continuan_si_el_modelo_falla(self):
        self.documentos.side_effect = busqueda_semantica.ModeloNoDisponible('sin modelo')
        self.assertEqual(tareas.ejecutar()['vectores_actualizados'], 0)

    @override_settings(BUSQUEDA_SEMANTICA=False)
    def test_tareas_sin_busqueda_semantica(self):
        self.assertEqual(tareas.ejecutar()['vectores_actualizados'], 0)
        self.documentos.assert_not_called()

    def test_comando_indexar(self):
        salida = StringIO()
        call_command('indexar_busqueda', stdout=salida)
        self.assertIn('Vectores actualizados: 3', salida.getvalue())


class CargaModeloTests(LeicaTestCase):

    def setUp(self):
        estado = patch.multiple(busqueda_semantica, _modelo=None, _reintentar_desde=0.0)
        estado.start()
        self.addCleanup(estado.stop)

    @patch('fastembed.TextEmbedding', side_effect=OSError('sin red'))
    def test_fallo_de_carga_espera_antes_de_reintentar(self, constructor):
        for _ in range(2):
            with self.assertRaises(busqueda_semantica.ModeloNoDisponible):
                busqueda_semantica.vectorizar_consulta('osciloscopio')
        constructor.assert_called_once()

    @patch('fastembed.TextEmbedding')
    def test_carga_el_modelo_una_sola_vez_y_normaliza(self, constructor):
        constructor.return_value.embed.side_effect = lambda textos: iter([np.array([3.0, 4.0])] * len(textos))
        vectores = busqueda_semantica.vectorizar_documentos(['a', 'b'])
        consulta = busqueda_semantica.vectorizar_consulta('a')
        constructor.assert_called_once()
        np.testing.assert_allclose(consulta, [0.6, 0.8])
        np.testing.assert_allclose(vectores, [[0.6, 0.8], [0.6, 0.8]])
        textos = [c.args[0] for c in constructor.return_value.embed.call_args_list]
        self.assertEqual(textos, [
            ['title: none | text: a', 'title: none | text: b'], ['task: search result | query: a'],
        ])
