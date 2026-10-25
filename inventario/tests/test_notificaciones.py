from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.test import override_settings
from django.utils import timezone

from inventario import tareas
from inventario.models import Equipo, Solicitud, SolicitudItem

from .base import LeicaTestCase


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', URL_SITIO='https://leica.example.cl')
class CorreosSolicitudTests(LeicaTestCase):

    def setUp(self):
        self.client.force_login(self.encargado)

    def test_aprobar_envia_correo_al_solicitante(self):
        s = self.crear_solicitud(self.estudiante, equipos=[self.crear_equipo(nombre='Osciloscopio')])
        with self.captureOnCommitCallbacks(execute=True):
            self.accion_solicitud(s, 'aprobar')
        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        self.assertEqual(correo.to, ['estudiante@inacapmail.cl'])
        self.assertIn(f'#{s.id} aprobada', correo.subject)
        self.assertIn('Osciloscopio', correo.body)
        self.assertIn('https://leica.example.cl/solicitudes/', correo.body)

    def test_rechazar_envia_correo(self):
        s = self.crear_solicitud(self.estudiante)
        with self.captureOnCommitCallbacks(execute=True):
            self.accion_solicitud(s, 'rechazar')
        self.assertIn('rechazada', mail.outbox[0].subject)

    def test_representacion_avisa_a_ambos(self):
        s = self.crear_solicitud(self.docente)
        Solicitud.objects.filter(id=s.id).update(en_representacion_de=self.estudiante)
        with self.captureOnCommitCallbacks(execute=True):
            self.accion_solicitud(s, 'aprobar')
        self.assertEqual(mail.outbox[0].to, ['docente@inacapmail.cl', 'estudiante@inacapmail.cl'])

    def test_accion_fallida_no_envia(self):
        s = self.crear_solicitud(self.estudiante, estado=Solicitud.EstadoSolicitud.DEVUELTA)
        with self.captureOnCommitCallbacks(execute=True):
            self.accion_solicitud(s, 'aprobar')
        self.assertEqual(mail.outbox, [])

    def test_error_smtp_no_impide_aprobar(self):
        s = self.crear_solicitud(self.estudiante)
        with patch('inventario.notificaciones.send_mail', side_effect=OSError('sin conexión')), \
                self.captureOnCommitCallbacks(execute=True):
            self.accion_solicitud(s, 'aprobar')
        s.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.APROBADA)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', HORAS_RECORDATORIO=24)
class AvisosProgramadosTests(LeicaTestCase):

    def entregada(self, fin):
        return self.crear_solicitud(self.estudiante, inicio=fin - timedelta(hours=2), fin=fin,
                                    estado=Solicitud.EstadoSolicitud.ENTREGADA)

    def test_recordatorio_antes_del_vencimiento_una_sola_vez(self):
        s = self.entregada(timezone.now() + timedelta(hours=5))
        self.entregada(timezone.now() + timedelta(days=3))
        self.assertEqual(tareas.ejecutar()['recordatorios_enviados'], 1)
        self.assertEqual(tareas.ejecutar()['recordatorios_enviados'], 0)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(f'#{s.id}', mail.outbox[0].subject)

    def test_aviso_de_atraso_una_sola_vez(self):
        s = self.entregada(timezone.now() - timedelta(hours=1))
        resultado = tareas.ejecutar()
        self.assertEqual((resultado['atrasadas_marcadas'], resultado['avisos_atraso_enviados']), (1, 1))
        self.assertEqual(tareas.ejecutar()['avisos_atraso_enviados'], 0)
        self.assertIn('atrasado', mail.outbox[0].subject)
        s.refresh_from_db()
        self.assertIsNotNone(s.aviso_atraso_enviado)

    def test_si_falla_el_envio_se_reintenta(self):
        s = self.entregada(timezone.now() - timedelta(hours=1))
        with patch('inventario.notificaciones.send_mail', side_effect=OSError('sin conexión')):
            self.assertEqual(tareas.ejecutar()['avisos_atraso_enviados'], 0)
        s.refresh_from_db()
        self.assertIsNone(s.aviso_atraso_enviado)
        self.assertEqual(tareas.ejecutar()['avisos_atraso_enviados'], 1)


class DevolucionPorItemTests(LeicaTestCase):

    def test_cada_equipo_recibe_su_estado(self):
        bueno = self.crear_equipo('D-1', estado=Equipo.Estado.PRESTADO)
        roto = self.crear_equipo('D-2', estado=Equipo.Estado.PRESTADO)
        s = self.crear_solicitud(self.estudiante, equipos=[bueno, roto], estado=Solicitud.EstadoSolicitud.ENTREGADA)
        item_bueno, item_roto = s.items.order_by('id')
        self.client.force_login(self.encargado)
        self.accion_solicitud(s, 'devolver', **{f'estado_item_{item_bueno.id}': 'bueno', f'estado_item_{item_roto.id}': 'dañado'})
        bueno.refresh_from_db()
        roto.refresh_from_db()
        self.assertEqual(bueno.estado, Equipo.Estado.DISPONIBLE)
        self.assertEqual(roto.estado, Equipo.Estado.EN_MANTENIMIENTO)
        self.assertEqual(
            list(s.items.order_by('id').values_list('estado_devolucion', flat=True)),
            [SolicitudItem.EstadoDevolucion.BUENO, SolicitudItem.EstadoDevolucion.DANADO],
        )
        self.assertEqual(s.movimientos.get(tipo='devolucion').estado_equipo, 'dañado')

    def test_estado_invalido_en_un_item_no_devuelve_nada(self):
        e = self.crear_equipo(estado=Equipo.Estado.PRESTADO)
        s = self.crear_solicitud(self.estudiante, equipos=[e], estado=Solicitud.EstadoSolicitud.ENTREGADA)
        self.client.force_login(self.encargado)
        self.accion_solicitud(s, 'devolver', **{f'estado_item_{s.items.get().id}': 'perdido'})
        s.refresh_from_db()
        e.refresh_from_db()
        self.assertEqual((s.estado, e.estado), (Solicitud.EstadoSolicitud.ENTREGADA, Equipo.Estado.PRESTADO))
