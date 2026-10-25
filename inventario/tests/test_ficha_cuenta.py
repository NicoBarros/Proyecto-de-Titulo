from datetime import timedelta
from unittest.mock import patch

import qrcode
from django.test import override_settings
from django.utils import timezone

from inventario.models import Equipo, EventoSeguridad, Mantenimiento, Solicitud

from .base import LeicaTestCase


class FichaEquipoTests(LeicaTestCase):

    def test_todos_los_roles_ven_la_ficha(self):
        e = self.crear_equipo()
        for u in (self.estudiante, self.docente, self.comite, self.encargado):
            with self.subTest(rol=u.rol):
                self.client.force_login(u)
                self.assertEqual(self.client.get(f'/inventario/equipo/{e.id}/').status_code, 200)

    def test_estudiante_no_ve_datos_tecnicos(self):
        e = self.crear_equipo()
        Mantenimiento.objects.create(equipo=e, falla_descrita='Pantalla rota')
        self.client.force_login(self.estudiante)
        r = self.client.get(f'/inventario/equipo/{e.id}/')
        self.assertNotIn('mantenimientos', r.context)
        self.assertNotContains(r, 'Pantalla rota')
        self.assertNotContains(r, 'Valor de adquisición')
        self.assertNotContains(r, '/qr/')

    def test_encargado_ve_mantenimientos_historial_y_qr(self):
        e = self.crear_equipo()
        Mantenimiento.objects.create(equipo=e, falla_descrita='Pantalla rota')
        self.client.force_login(self.encargado)
        r = self.client.get(f'/inventario/equipo/{e.id}/')
        self.assertContains(r, 'Pantalla rota')
        self.assertContains(r, f'/inventario/equipo/{e.id}/qr/')

    def test_boton_solicitar_solo_si_esta_disponible(self):
        disponible = self.crear_equipo('F-1')
        prestado = self.crear_equipo('F-2', estado=Equipo.Estado.PRESTADO)
        self.client.force_login(self.estudiante)
        self.assertContains(self.client.get(f'/inventario/equipo/{disponible.id}/'), f'?equipo={disponible.id}')
        self.assertNotContains(self.client.get(f'/inventario/equipo/{prestado.id}/'), f'?equipo={prestado.id}')

    def test_muestra_reservas_futuras_y_omite_pasadas(self):
        e = self.crear_equipo()
        futura = timezone.now() + timedelta(days=2)
        pasada = timezone.now() - timedelta(days=5)
        self.crear_solicitud(self.estudiante, equipos=[e], inicio=futura, estado=Solicitud.EstadoSolicitud.APROBADA)
        self.crear_solicitud(self.estudiante, equipos=[e], inicio=pasada, estado=Solicitud.EstadoSolicitud.DEVUELTA)
        self.client.force_login(self.estudiante)
        self.assertEqual(len(self.client.get(f'/inventario/equipo/{e.id}/').context['reservas']), 1)

    def test_preselecciona_el_equipo_en_solicitudes(self):
        e = self.crear_equipo()
        self.client.force_login(self.estudiante)
        r = self.client.get('/solicitudes/', {'equipo': e.id})
        self.assertContains(r, f'value="equipo:{e.id}" data-tipo="equipo" data-stock="1" selected')

    def test_qr_apunta_a_la_ficha(self):
        e = self.crear_equipo()
        self.client.force_login(self.encargado)
        with override_settings(URL_SITIO='https://leica.example.cl'), \
                patch('inventario.views.inventario.qrcode.make', wraps=qrcode.make) as make:
            self.client.get(f'/inventario/equipo/{e.id}/qr/')
        self.assertEqual(make.call_args.args[0], f'https://leica.example.cl/inventario/equipo/{e.id}/')


class CambiarContrasenaTests(LeicaTestCase):

    def cambiar(self, actual, nueva, confirmacion=None):
        return self.client.post('/cuenta/contrasena/', {
            'old_password': actual, 'new_password1': nueva, 'new_password2': confirmacion or nueva,
        })

    def test_cambia_contrasena_y_mantiene_la_sesion(self):
        self.client.force_login(self.estudiante)
        r = self.cambiar('Leica2026!', 'Laboratorio#2026')
        self.assertRedirects(r, '/')
        self.estudiante.refresh_from_db()
        self.assertTrue(self.estudiante.check_password('Laboratorio#2026'))
        self.assertEqual(self.client.get('/').status_code, 200)
        evento = EventoSeguridad.objects.get(tipo=EventoSeguridad.Tipo.CAMBIO_CUENTA)
        self.assertEqual(evento.usuario, self.estudiante)

    def test_rechaza_contrasena_actual_incorrecta(self):
        self.client.force_login(self.estudiante)
        r = self.cambiar('incorrecta', 'Laboratorio#2026')
        self.assertEqual(r.status_code, 200)
        self.estudiante.refresh_from_db()
        self.assertTrue(self.estudiante.check_password('Leica2026!'))

    def test_aplica_validadores(self):
        self.client.force_login(self.estudiante)
        self.cambiar('Leica2026!', '12345678')
        self.estudiante.refresh_from_db()
        self.assertTrue(self.estudiante.check_password('Leica2026!'))

    def test_requiere_sesion(self):
        self.assertEqual(self.client.get('/cuenta/contrasena/').status_code, 302)
