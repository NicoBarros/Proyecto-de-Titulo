from datetime import timedelta

from django.utils import timezone

from inventario.models import Solicitud

from .base import LeicaTestCase


def fmt(dt):
    return timezone.localtime(dt).strftime('%Y-%m-%dT%H:%M')


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


class ItemsRepetidosTests(LeicaTestCase):

    def pedir(self, items, cantidades):
        inicio = timezone.now() + timedelta(days=1)
        self.client.force_login(self.estudiante)
        return self.client.post('/solicitudes/', {
            'item[]': items, 'cantidad[]': cantidades, 'lugar_uso': 'dentro_sede',
            'horario_inicio': fmt(inicio), 'horario_fin': fmt(inicio + timedelta(hours=2)),
        }, follow=True)

    def test_rechaza_el_mismo_equipo_dos_veces(self):
        e = self.crear_equipo()
        r = self.pedir([f'equipo:{e.id}', f'equipo:{e.id}'], ['1', '1'])
        self.assertFalse(Solicitud.objects.exists())
        self.assertContains(r, 'No puedes repetir el mismo equipo')

    def test_insumo_repetido_suma_cantidades(self):
        i = self.crear_insumo(cantidad=10)
        self.pedir([f'insumo:{i.id}', f'insumo:{i.id}'], ['2', '3'])
        item = Solicitud.objects.get().items.get()
        self.assertEqual(item.cantidad, 5)

    def test_insumo_agotado_queda_marcado(self):
        self.crear_insumo('Agotado', cantidad=0)
        self.client.force_login(self.estudiante)
        self.assertContains(self.client.get('/solicitudes/'), 'data-agotado="1" disabled')

