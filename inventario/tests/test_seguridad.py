import os
import re
import subprocess
import sys

from django.conf import settings
from django.core.management.utils import get_random_secret_key
from django.test import RequestFactory, SimpleTestCase, override_settings

from inventario.models import EventoSeguridad
from inventario.seguridad import ip_cliente
from .base import LeicaTestCase

CLAVE = 'Leica2026!'


class RegistroEventosTests(LeicaTestCase):

    def login(self, email, password, ip='10.0.0.1'):
        return self.client.post('/login/', {'username': email, 'password': password}, REMOTE_ADDR=ip)

    def test_inicio_y_cierre_de_sesion(self):
        self.login('docente@inacapmail.cl', CLAVE)
        self.client.post('/logout/', REMOTE_ADDR='10.0.0.1')
        inicio, cierre = EventoSeguridad.objects.order_by('id')
        self.assertEqual(inicio.tipo, EventoSeguridad.Tipo.INICIO_SESION)
        self.assertEqual(inicio.usuario, self.docente)
        self.assertEqual(inicio.ip, '10.0.0.1')
        self.assertEqual(cierre.tipo, EventoSeguridad.Tipo.CIERRE_SESION)
        self.assertEqual(cierre.usuario, self.docente)

    def test_intento_fallido_registra_el_correo_sin_la_clave(self):
        self.login('Docente@InacapMail.cl', 'incorrecta')
        evento = EventoSeguridad.objects.get()
        self.assertEqual(evento.tipo, EventoSeguridad.Tipo.INTENTO_FALLIDO)
        self.assertEqual(evento.identificador, 'docente@inacapmail.cl')
        self.assertIsNone(evento.usuario)
        self.assertNotIn('incorrecta', f'{evento.detalle}{evento.identificador}')

    def test_acceso_denegado_queda_registrado(self):
        self.client.force_login(self.estudiante)
        r = self.client.get('/mantenimiento/', REMOTE_ADDR='10.0.0.7')
        self.assertEqual(r.status_code, 403)
        evento = EventoSeguridad.objects.get(tipo=EventoSeguridad.Tipo.ACCESO_DENEGADO)
        self.assertEqual(evento.usuario, self.estudiante)
        self.assertEqual(evento.ruta, '/mantenimiento/')
        self.assertEqual(evento.ip, '10.0.0.7')


class BloqueoPorIntentosTests(LeicaTestCase):

    def login(self, email, password, ip='10.0.0.1'):
        return self.client.post('/login/', {'username': email, 'password': password}, REMOTE_ADDR=ip)

    def fallar(self, veces, email='estudiante@inacapmail.cl', ip='10.0.0.1'):
        for _ in range(veces):
            self.login(email, 'incorrecta', ip)

    def test_bloquea_tras_el_limite_incluso_con_la_clave_correcta(self):
        self.fallar(settings.AXES_FAILURE_LIMIT)
        r = self.login('estudiante@inacapmail.cl', CLAVE)
        self.assertEqual(r.status_code, 429)
        self.assertTemplateUsed(r, 'inventario/bloqueo.html')
        self.assertContains(r, '15 minutos', status_code=429)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertTrue(EventoSeguridad.objects.filter(
            tipo=EventoSeguridad.Tipo.BLOQUEO, identificador='estudiante@inacapmail.cl',
        ).exists())

    def test_variar_mayusculas_no_evita_el_bloqueo(self):
        for email in ('ESTUDIANTE@inacapmail.cl', 'Estudiante@inacapmail.cl', 'estudiante@INACAPMAIL.cl',
                      'estudiante@inacapmail.cl', 'EsTuDiAnTe@inacapmail.cl'):
            self.login(email, 'incorrecta')
        self.assertEqual(self.login('estudiante@inacapmail.cl', CLAVE).status_code, 429)

    def test_el_bloqueo_no_afecta_a_otros_equipos_ni_a_otras_cuentas(self):
        self.fallar(settings.AXES_FAILURE_LIMIT)
        self.assertEqual(self.login('estudiante@inacapmail.cl', CLAVE, ip='10.0.0.2').status_code, 302)
        self.client.logout()
        self.assertEqual(self.login('docente@inacapmail.cl', CLAVE).status_code, 302)

    def test_inicio_exitoso_reinicia_el_contador(self):
        self.fallar(settings.AXES_FAILURE_LIMIT - 1)
        self.assertEqual(self.login('estudiante@inacapmail.cl', CLAVE).status_code, 302)
        self.client.logout()
        self.fallar(settings.AXES_FAILURE_LIMIT - 1)
        self.assertEqual(self.login('estudiante@inacapmail.cl', CLAVE).status_code, 302)


class SesionTests(LeicaTestCase):

    def test_expira_por_inactividad_y_al_cerrar_el_navegador(self):
        self.client.post('/login/', {'username': 'docente@inacapmail.cl', 'password': CLAVE})
        r = self.client.get('/')
        self.assertEqual(self.client.session.get_expiry_age(), 60 * 60)
        self.assertTrue(self.client.session.get_expire_at_browser_close())
        self.assertEqual(r.cookies[settings.SESSION_COOKIE_NAME]['expires'], '')

    def test_plantillas_verifican_la_integridad_de_los_recursos_externos(self):
        r = self.client.get('/login/')
        etiquetas = re.findall(r'<(?:link|script)[^>]+https://cdn[^>]+>', r.content.decode())
        self.assertGreaterEqual(len(etiquetas), 3)
        for etiqueta in etiquetas:
            with self.subTest(etiqueta=etiqueta):
                self.assertRegex(etiqueta, r'integrity="sha384-[A-Za-z0-9+/=]{64}"')
                self.assertIn('crossorigin="anonymous"', etiqueta)


class IpClienteTests(SimpleTestCase):

    def ip(self, **meta):
        return ip_cliente(RequestFactory().get('/', **meta))

    @override_settings(PROXY_CONFIABLE=True)
    def test_detras_del_proxy_usa_la_ultima_ip_reenviada_sin_puerto(self):
        self.assertEqual(self.ip(HTTP_X_FORWARDED_FOR='1.1.1.1, 200.27.10.5:51234', REMOTE_ADDR='169.254.0.1'), '200.27.10.5')
        self.assertEqual(self.ip(HTTP_X_FORWARDED_FOR='[2001:db8::1]:443'), '2001:db8::1')
        self.assertEqual(self.ip(HTTP_X_FORWARDED_FOR='2001:db8::2'), '2001:db8::2')
        self.assertIsNone(self.ip(HTTP_X_FORWARDED_FOR='no-es-una-ip'))

    @override_settings(PROXY_CONFIABLE=False)
    def test_sin_proxy_ignora_la_cabecera_reenviada(self):
        self.assertEqual(self.ip(HTTP_X_FORWARDED_FOR='1.1.1.1', REMOTE_ADDR='10.0.0.9'), '10.0.0.9')


class ConfiguracionProduccionTests(SimpleTestCase):

    def test_check_deploy_sin_advertencias_de_seguridad_de_transporte(self):
        entorno = {
            **os.environ, 'DEBUG': 'False', 'SECRET_KEY': get_random_secret_key(),
            'WEBSITE_HOSTNAME': 'leica-inventario.azurewebsites.net', 'PYTHONUTF8': '1',
        }
        resultado = subprocess.run(
            [sys.executable, 'manage.py', 'check', '--deploy'], env=entorno,
            cwd=settings.BASE_DIR, capture_output=True, text=True,
        )
        salida = resultado.stdout + resultado.stderr
        self.assertEqual(resultado.returncode, 0, salida)
        self.assertIn('no issues', salida)
