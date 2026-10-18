"""
RF-11 / RNF-06: Busqueda asistida por IA (Gemini) con respaldo local por palabras clave.
Gemini se simula con mocks: los tests nunca llaman a la API real.
"""
from unittest.mock import patch, MagicMock

from django.test import override_settings

from inventario.models import Equipo
from .base import LeicaTestCase


class BusquedaTests(LeicaTestCase):

    def setUp(self):
        self.client.force_login(self.estudiante)
        self.osc = self.crear_equipo('B-1', 'Osciloscopio', especificaciones='50 MHz dos canales')
        self.mul = self.crear_equipo('B-2', 'Multimetro digital', especificaciones='True RMS')
        self.crear_equipo('B-3', 'Osciloscopio prestado', estado=Equipo.Estado.PRESTADO)

    def buscar(self, consulta):
        return self.client.post('/busqueda/', {'consulta': consulta}).json()

    def test_get_muestra_pagina(self):
        self.assertEqual(self.client.get('/busqueda/').status_code, 200)

    def test_consulta_vacia(self):
        r = self.client.post('/busqueda/', {'consulta': ''})
        self.assertEqual(r.status_code, 400)

    def test_busqueda_local_sin_api_key(self):
        data = self.buscar('osciloscopio canales')
        self.assertEqual(data['fuente'], 'palabras_clave_local')
        self.assertEqual([r['codigo_inventario'] for r in data['resultados']], ['B-1'])

    def test_busqueda_local_ignora_equipos_no_disponibles(self):
        codigos = [r['codigo_inventario'] for r in self.buscar('osciloscopio')['resultados']]
        self.assertNotIn('B-3', codigos)

    def test_busqueda_local_sin_coincidencias(self):
        self.assertEqual(self.buscar('impresora 3d')['resultados'], [])

    @override_settings(GEMINI_API_KEY='clave-falsa')
    @patch('google.genai.Client')
    def test_usa_respuesta_de_gemini(self, client_cls):
        client_cls.return_value.models.generate_content.return_value = MagicMock(
            text=f'```json\n[{self.mul.id}, 9999, {self.osc.id}]\n```')
        data = self.buscar('algo para medir voltaje')
        self.assertEqual(data['fuente'], 'ia_gemini')
        # ids inexistentes o no disponibles se descartan, se respeta el orden de la IA
        self.assertEqual([r['codigo_inventario'] for r in data['resultados']], ['B-2', 'B-1'])

    @override_settings(GEMINI_API_KEY='clave-falsa')
    @patch('google.genai.Client')
    def test_no_expone_equipos_no_disponibles_aunque_la_ia_los_devuelva(self, client_cls):
        prestado = Equipo.objects.get(codigo_inventario='B-3')
        client_cls.return_value.models.generate_content.return_value = MagicMock(text=f'[{prestado.id}]')
        self.assertNotIn('B-3', [r['codigo_inventario'] for r in self.buscar('osciloscopio')['resultados']])

    @override_settings(GEMINI_API_KEY='clave-falsa')
    @patch('google.genai.Client')
    def test_si_gemini_falla_cae_a_busqueda_local(self, client_cls):
        client_cls.return_value.models.generate_content.side_effect = RuntimeError('sin red')
        data = self.buscar('multimetro')
        self.assertEqual(data['fuente'], 'palabras_clave_local')
        self.assertEqual([r['codigo_inventario'] for r in data['resultados']], ['B-2'])

    @override_settings(GEMINI_API_KEY='clave-falsa')
    @patch('google.genai.Client')
    def test_respuesta_no_json_cae_a_busqueda_local(self, client_cls):
        client_cls.return_value.models.generate_content.return_value = MagicMock(text='No se que decirte')
        self.assertEqual(self.buscar('multimetro')['fuente'], 'palabras_clave_local')
