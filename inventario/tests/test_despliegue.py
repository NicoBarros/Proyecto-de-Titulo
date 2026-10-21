import json
import os
import subprocess
import sys
from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.db import OperationalError
from django.test import SimpleTestCase, override_settings

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


class SaludTests(LeicaTestCase):

    def test_responde_ok_con_base_disponible(self):
        r = self.client.get('/salud/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {'estado': 'ok', 'base_de_datos': 'ok'})
        self.assertIn('no-cache', r['Cache-Control'])

    def test_responde_503_si_la_base_no_responde(self):
        with patch('inventario.middleware.connection.cursor', side_effect=OperationalError('sin conexión')), \
                self.assertLogs('inventario.middleware', level='ERROR'):
            r = self.client.get('/salud/')
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()['estado'], 'error')

    @override_settings(SECURE_SSL_REDIRECT=True, ALLOWED_HOSTS=['leica.azurewebsites.net'])
    def test_sondeos_internos_no_se_redirigen_ni_se_rechazan_por_dominio(self):
        r = self.client.get('/salud/', HTTP_HOST='10.0.0.4:8000')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get('/login/', HTTP_HOST='leica.azurewebsites.net').status_code, 301)

    def test_no_requiere_sesion(self):
        self.client.logout()
        self.assertEqual(self.client.get('/salud/').status_code, 200)


class ConfiguracionPlataformaTests(SimpleTestCase):

    def ajustes_con(self, **variables):
        entorno = {**os.environ, 'DEBUG': 'False', 'SECRET_KEY': 'x' * 50, **variables}
        codigo = ('import django, json; django.setup(); from django.conf import settings; '
                  'print(json.dumps([settings.ALLOWED_HOSTS, settings.CSRF_TRUSTED_ORIGINS]))')
        salida = subprocess.run(
            [sys.executable, '-c', codigo], env={**entorno, 'DJANGO_SETTINGS_MODULE': 'leica_project.settings'},
            cwd=settings.BASE_DIR, capture_output=True, text=True, check=True,
        ).stdout
        return json.loads(salida)

    def test_reconoce_el_dominio_de_azure(self):
        hosts, origenes = self.ajustes_con(WEBSITE_HOSTNAME='leica-inventario.azurewebsites.net')
        self.assertIn('leica-inventario.azurewebsites.net', hosts)
        self.assertIn('https://leica-inventario.azurewebsites.net', origenes)
