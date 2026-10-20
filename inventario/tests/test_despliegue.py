import os
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command

from inventario.models import Usuario
from .base import LeicaTestCase


class CrearAdminTests(LeicaTestCase):

    def ejecutar(self, **env):
        salida = StringIO()
        with patch.dict(os.environ, env, clear=False):
            call_command('crear_admin', stdout=salida)
        return salida.getvalue()

    def test_sin_variables_no_crea_nada(self):
        with patch.dict(os.environ, {}, clear=True):
            salida = StringIO()
            call_command('crear_admin', stdout=salida)
        self.assertIn('no se crea el administrador', salida.getvalue())

    def test_crea_superusuario_encargado(self):
        self.ejecutar(ADMIN_EMAIL='Jefe@inacapmail.cl', ADMIN_PASSWORD='ClaveSegura2026')
        u = Usuario.objects.get(email='jefe@inacapmail.cl')
        self.assertTrue(u.is_superuser and u.is_staff and u.is_active)
        self.assertEqual(u.rol, Usuario.Rol.ENCARGADO_LABORATORIO)
        self.assertTrue(u.check_password('ClaveSegura2026'))

    def test_es_idempotente_y_no_cambia_la_clave(self):
        self.ejecutar(ADMIN_EMAIL='jefe@inacapmail.cl', ADMIN_PASSWORD='Primera2026')
        salida = self.ejecutar(ADMIN_EMAIL='jefe@inacapmail.cl', ADMIN_PASSWORD='Otra2026')
        self.assertIn('ya existe', salida)
        self.assertEqual(Usuario.objects.filter(email='jefe@inacapmail.cl').count(), 1)
        self.assertTrue(Usuario.objects.get(email='jefe@inacapmail.cl').check_password('Primera2026'))

    def test_promueve_un_usuario_existente(self):
        self.ejecutar(ADMIN_EMAIL='docente@inacapmail.cl', ADMIN_PASSWORD='x')
        self.docente.refresh_from_db()
        self.assertTrue(self.docente.is_superuser)
        self.assertEqual(self.docente.rol, Usuario.Rol.ENCARGADO_LABORATORIO)

    def test_username_repetido_recibe_sufijo(self):
        self.ejecutar(ADMIN_EMAIL='estudiante@otro.cl', ADMIN_PASSWORD='ClaveSegura2026')
        self.assertEqual(Usuario.objects.get(email='estudiante@otro.cl').username, 'estudiante_1')
