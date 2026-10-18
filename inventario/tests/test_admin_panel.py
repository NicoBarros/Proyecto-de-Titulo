"""
Panel de administracion institucional y reportes (RF-13).
"""
from datetime import timedelta
from unittest import expectedFailure

from django.utils import timezone

from inventario.models import Usuario, Equipo, Solicitud
from .base import LeicaTestCase


class PanelAdminTests(LeicaTestCase):

    def setUp(self):
        self.client.force_login(self.encargado)

    def post(self, **data):
        return self.client.post('/panel-admin/', data)

    def test_crear_usuario_institucional(self):
        self.post(accion='crear_usuario', email='Nuevo@InacapMail.cl', first_name='Ana',
                  rol='docente', password='secreta123')
        u = Usuario.objects.get(email='nuevo@inacapmail.cl')
        self.assertEqual(u.rol, 'docente')
        self.assertTrue(u.check_password('secreta123'))

    def test_rechaza_dominio_externo(self):
        self.post(accion='crear_usuario', email='x@gmail.com', rol='docente', password='secreta123')
        self.assertFalse(Usuario.objects.filter(email='x@gmail.com').exists())

    def test_rechaza_password_corta(self):
        self.post(accion='crear_usuario', email='corta@inacapmail.cl', rol='docente', password='123')
        self.assertFalse(Usuario.objects.filter(email='corta@inacapmail.cl').exists())

    def test_username_repetido_recibe_sufijo(self):
        # 'estudiante' ya existe como username
        self.post(accion='crear_usuario', email='estudiante@alumnos.inacapmail.cl', rol='estudiante', password='secreta123')
        self.post(accion='crear_usuario', email='docente@inacapmail.cl', rol='docente', password='secreta123')  # email duplicado
        self.assertEqual(Usuario.objects.filter(email='docente@inacapmail.cl').count(), 1)

    def test_cambiar_rol(self):
        self.post(accion='cambiar_rol', user_id=self.estudiante.id, nuevo_rol='docente')
        self.estudiante.refresh_from_db()
        self.assertEqual(self.estudiante.rol, 'docente')

    def test_toggle_activo_y_no_puede_desactivarse_a_si_mismo(self):
        self.post(accion='toggle_activo', user_id=self.docente.id)
        self.docente.refresh_from_db()
        self.assertFalse(self.docente.is_active)
        self.post(accion='toggle_activo', user_id=self.encargado.id)
        self.encargado.refresh_from_db()
        self.assertTrue(self.encargado.is_active)

    def test_desbloquear(self):
        self.estudiante.bloqueado_hasta = timezone.now() + timedelta(days=3)
        self.estudiante.save()
        self.post(accion='desbloquear', user_id=self.estudiante.id)
        self.estudiante.refresh_from_db()
        self.assertFalse(self.estudiante.esta_bloqueado())

    def test_reset_password(self):
        self.post(accion='reset_password', user_id=self.docente.id, nueva_password='NuevaClave1')
        self.docente.refresh_from_db()
        self.assertTrue(self.docente.check_password('NuevaClave1'))

    def test_cambiar_estado_equipo(self):
        e = self.crear_equipo()
        self.post(accion='cambiar_estado_equipo', equipo_id=e.id, nuevo_estado='fuera_servicio')
        e.refresh_from_db()
        self.assertEqual((e.estado, e.version), (Equipo.Estado.FUERA_SERVICIO, 2))

    def test_metricas(self):
        self.estudiante.bloqueado_hasta = timezone.now() + timedelta(days=1)
        self.estudiante.save()
        m = self.client.get('/panel-admin/').context['metricas']
        self.assertEqual(m['total_usuarios'], 6)
        self.assertEqual(m['bloqueados'], 1)

    @expectedFailure
    def test_bug_staff_no_superusuario_puede_resetear_password_de_superusuario(self):
        """El seed da is_staff a docente/director; el panel solo exige is_staff -> escalada de privilegios."""
        admin = self.crear_usuario('admin', Usuario.Rol.ENCARGADO_LABORATORIO, is_staff=True, is_superuser=True)
        docente_staff = self.crear_usuario('docstaff', Usuario.Rol.DOCENTE, is_staff=True)
        self.client.force_login(docente_staff)
        self.post(accion='reset_password', user_id=admin.id, nueva_password='tomado123')
        admin.refresh_from_db()
        self.assertFalse(admin.check_password('tomado123'))

    @expectedFailure
    def test_bug_docente_staff_puede_aprobar_solicitudes(self):
        """docente no esta en ROLES_APROBADORES, pero is_staff lo habilita igual (views.py:213)."""
        docente_staff = self.crear_usuario('docstaff', Usuario.Rol.DOCENTE, is_staff=True)
        s = self.crear_solicitud(self.estudiante, equipos=[self.crear_equipo()])
        self.client.force_login(docente_staff)
        self.accion_solicitud(s, 'aprobar')
        s.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.PENDIENTE)

    @expectedFailure
    def test_bug_cambiar_rol_acepta_valores_invalidos(self):
        self.post(accion='cambiar_rol', user_id=self.estudiante.id, nuevo_rol='superadmin')
        self.estudiante.refresh_from_db()
        self.assertEqual(self.estudiante.rol, 'estudiante')

    @expectedFailure
    def test_bug_cambiar_estado_equipo_acepta_valores_invalidos(self):
        e = self.crear_equipo()
        self.post(accion='cambiar_estado_equipo', equipo_id=e.id, nuevo_estado='inventado')
        e.refresh_from_db()
        self.assertEqual(e.estado, Equipo.Estado.DISPONIBLE)


class ReportesTests(LeicaTestCase):

    def test_reportes_contenido(self):
        usado = self.crear_equipo('R-1', 'Usado')
        self.crear_equipo('R-2', 'Sin uso')
        inicio = timezone.now() - timedelta(days=3)
        self.crear_solicitud(self.estudiante, equipos=[usado], inicio=inicio, fin=inicio + timedelta(hours=1),
                             estado=Solicitud.EstadoSolicitud.ENTREGADA)
        self.client.force_login(self.director)
        r = self.client.get('/reportes/', {'dias': '30'})
        self.assertEqual(r.context['top_equipos'][0].codigo_inventario, 'R-1')
        self.assertEqual(r.context['vencidos'].count(), 1)
        self.assertEqual([e.codigo_inventario for e in r.context['sin_movimiento']], ['R-2'])

    def test_dias_invalido_usa_90(self):
        self.client.force_login(self.director)
        self.assertEqual(self.client.get('/reportes/', {'dias': 'abc'}).context['dias'], 90)


class DashboardTests(LeicaTestCase):

    def test_totales(self):
        self.crear_equipo('D-1')
        self.crear_equipo('D-2', estado=Equipo.Estado.PRESTADO)
        i = self.crear_insumo(cantidad=10, umbral=5)
        i.cantidad_disponible = 1
        i.save()
        self.client.force_login(self.estudiante)
        t = self.client.get('/').context['totales']
        self.assertEqual((t['total_equipos'], t['equipos_disponibles'], t['equipos_prestados'], t['insumos_bajo_stock']),
                         (2, 1, 1, 1))
