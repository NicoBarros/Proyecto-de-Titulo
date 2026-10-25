from .base import LeicaTestCase


class VistaItemsSolicitudTests(LeicaTestCase):

    def test_muestra_tres_items_y_agrupa_el_resto(self):
        equipos = [self.crear_equipo(f'K-{i}', nombre=f'Equipo {i}') for i in range(5)]
        insumo = self.crear_insumo()
        self.crear_solicitud(self.estudiante, equipos=equipos, insumos=[(insumo, 3)])
        self.client.force_login(self.encargado)
        html = self.client.get('/solicitudes/').content.decode()
        self.assertIn('<summary>+3 más</summary>', html)
        self.assertIn('Protoboard <span class="text-muted">×3</span>', html)
        self.assertEqual(html.count('class="item-linea"'), 6)

    def test_sin_desplegable_con_pocos_items(self):
        self.crear_solicitud(self.estudiante, equipos=[self.crear_equipo()])
        self.client.force_login(self.encargado)
        self.assertNotIn('items-mas', self.client.get('/solicitudes/').content.decode())
