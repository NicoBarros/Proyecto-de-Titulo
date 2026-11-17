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
