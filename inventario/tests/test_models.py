from datetime import timedelta

from django.db import IntegrityError
from django.utils import timezone

from inventario.models import Equipo, SolicitudItem, Usuario

from .base import LeicaTestCase


class UsuarioModelTests(LeicaTestCase):

    def test_login_se_hace_con_email(self):
        self.assertEqual(Usuario.USERNAME_FIELD, 'email')

    def test_email_es_unico(self):
        with self.assertRaises(IntegrityError):
            Usuario.objects.create_user(username='otro', email='estudiante@inacapmail.cl', password='x')

    def test_rol_por_defecto_es_estudiante(self):
        u = Usuario.objects.create_user(username='nuevo', email='nuevo@inacapmail.cl', password='x')
        self.assertEqual(u.rol, Usuario.Rol.ESTUDIANTE)

    def test_esta_bloqueado(self):
        u = self.estudiante
        self.assertFalse(u.esta_bloqueado())
        u.bloqueado_hasta = timezone.now() + timedelta(days=1)
        self.assertTrue(u.esta_bloqueado())
        u.bloqueado_hasta = timezone.now() - timedelta(seconds=1)
        self.assertFalse(u.esta_bloqueado())


class EquipoModelTests(LeicaTestCase):

    def test_valores_por_defecto(self):
        e = self.crear_equipo()
        self.assertEqual(e.estado, Equipo.Estado.DISPONIBLE)
        self.assertEqual(e.version, 1)

    def test_codigo_inventario_unico(self):
        self.crear_equipo(codigo='X-1')
        with self.assertRaises(IntegrityError):
            self.crear_equipo(codigo='X-1')


class InsumoModelTests(LeicaTestCase):

    def test_bajo_stock_incluye_el_umbral(self):
        i = self.crear_insumo(cantidad=10, umbral=2)
        self.assertFalse(i.bajo_stock)
        i.cantidad_disponible = 2
        self.assertTrue(i.bajo_stock)
        i.cantidad_disponible = 0
        self.assertTrue(i.bajo_stock)


class InsumoNombreUnicoTests(LeicaTestCase):

    def test_nombre_de_insumo_es_unico(self):
        self.crear_insumo('Cables')
        with self.assertRaises(IntegrityError):
            self.crear_insumo('Cables')


class SolicitudItemModelTests(LeicaTestCase):

    def test_str_con_equipo_y_con_insumo(self):
        equipo = self.crear_equipo(nombre='Osciloscopio')
        insumo = self.crear_insumo(nombre='Cables')
        s = self.crear_solicitud(self.estudiante, equipos=[equipo], insumos=[(insumo, 3)])
        textos = sorted(str(item) for item in SolicitudItem.objects.filter(solicitud=s))
        self.assertEqual(textos, ['Cables x3', 'Osciloscopio x1'])
