import re

from inventario.models import Equipo, Mantenimiento, Solicitud

from .base import LeicaTestCase

SCRIPT = re.compile(r'<script\b([^>]*)>', re.IGNORECASE)
MANEJADOR = re.compile(r'<[^>]+\son[a-z]+\s*=', re.IGNORECASE)


class PoliticaSeguridadContenidoTests(LeicaTestCase):

    def politica(self, respuesta):
        return {
            directiva.split()[0]: directiva.split()[1:]
            for directiva in respuesta['Content-Security-Policy'].split(';') if directiva.strip()
        }

    def test_scripts_solo_desde_el_sitio_y_el_cdn(self):
        politica = self.politica(self.client.get('/login/'))
        self.assertEqual(politica['script-src'], ["'self'", 'https://cdn.jsdelivr.net'])
        self.assertEqual(politica['object-src'], ["'none'"])
        self.assertEqual(politica['frame-ancestors'], ["'none'"])

    def test_ninguna_pantalla_usa_javascript_inline(self):
        equipo = self.crear_equipo()
        Mantenimiento.objects.create(equipo=equipo)
        self.crear_solicitud(self.estudiante, equipos=[self.crear_equipo('E-2', estado=Equipo.Estado.PRESTADO)],
                             estado=Solicitud.EstadoSolicitud.ENTREGADA)
        self.encargado.is_superuser = True
        self.encargado.save()
        self.client.force_login(self.encargado)
        rutas = [
            '/', '/inventario/', '/inventario/?tab=insumos', f'/inventario/equipo/{equipo.id}/',
            f'/inventario/equipo/{equipo.id}/editar/', f'/inventario/equipo/{equipo.id}/historial/',
            '/inventario/importar/', '/solicitudes/', '/mantenimiento/', '/reportes/', '/busqueda/',
            '/panel-admin/', '/cuenta/contrasena/', '/admin/', '/admin/inventario/equipo/',
            f'/admin/inventario/equipo/{equipo.id}/change/',
        ]
        for ruta in rutas:
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta)
                self.assertEqual(respuesta.status_code, 200)
                html = respuesta.content.decode()
                for atributos in SCRIPT.findall(html):
                    if 'application/json' in atributos:
                        continue
                    self.assertIn('src=', atributos, f'Script inline en {ruta}')
                self.assertIsNone(MANEJADOR.search(html), f'Manejador de evento inline en {ruta}')

    def test_login_sin_javascript_inline(self):
        html = self.client.get('/login/').content.decode()
        self.assertTrue(all('src=' in a for a in SCRIPT.findall(html)))
        self.assertIsNone(MANEJADOR.search(html))
