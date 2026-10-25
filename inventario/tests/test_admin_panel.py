"""
Panel de administracion institucional y reportes (RF-13).
"""
from datetime import timedelta

from django.utils import timezone

from inventario.models import Equipo, Solicitud, Usuario

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

    def test_staff_no_puede_cambiarse_su_propio_rol(self):
        staff = self.crear_usuario('calstaff', Usuario.Rol.CONTROL_CALIDAD, is_staff=True)
        self.client.force_login(staff)
        self.post(accion='cambiar_rol', user_id=staff.id, nuevo_rol='encargado_laboratorio')
        staff.refresh_from_db()
        self.assertEqual(staff.rol, 'control_calidad')

    def test_staff_no_superusuario_no_crea_usuarios_staff(self):
        self.client.force_login(self.crear_usuario('calstaff', Usuario.Rol.CONTROL_CALIDAD, is_staff=True))
        self.post(accion='crear_usuario', email='nuevo.staff@inacapmail.cl', rol='docente',
                  password='secreta123', is_staff='on')
        self.assertFalse(Usuario.objects.get(email='nuevo.staff@inacapmail.cl').is_staff)

    def test_crear_usuario_con_rol_invalido(self):
        self.post(accion='crear_usuario', email='raro@inacapmail.cl', rol='superadmin', password='secreta123')
        self.assertFalse(Usuario.objects.filter(email='raro@inacapmail.cl').exists())

    def test_metricas(self):
        self.estudiante.bloqueado_hasta = timezone.now() + timedelta(days=1)
        self.estudiante.save()
        m = self.client.get('/panel-admin/').context['metricas']
        self.assertEqual(m['total_usuarios'], 6)
        self.assertEqual(m['bloqueados'], 1)

    def test_staff_no_puede_resetear_password_de_superusuario(self):
        """Un administrador staff (no superusuario) no puede tomar control de un superusuario."""
        admin = self.crear_usuario('admin', Usuario.Rol.ENCARGADO_LABORATORIO, is_staff=True, is_superuser=True)
        docente_staff = self.crear_usuario('docstaff', Usuario.Rol.DOCENTE, is_staff=True)
        self.client.force_login(docente_staff)
        self.post(accion='reset_password', user_id=admin.id, nueva_password='tomado123')
        admin.refresh_from_db()
        self.assertFalse(admin.check_password('tomado123'))

    def test_docente_staff_no_puede_aprobar(self):
        """Aprobar depende del rol (ROLES_APROBADORES), no de is_staff."""
        docente_staff = self.crear_usuario('docstaff', Usuario.Rol.DOCENTE, is_staff=True)
        s = self.crear_solicitud(self.estudiante, equipos=[self.crear_equipo()])
        self.client.force_login(docente_staff)
        self.accion_solicitud(s, 'aprobar')
        s.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.PENDIENTE)

    def test_cambiar_rol_rechaza_valores_invalidos(self):
        self.post(accion='cambiar_rol', user_id=self.estudiante.id, nuevo_rol='superadmin')
        self.estudiante.refresh_from_db()
        self.assertEqual(self.estudiante.rol, 'estudiante')

    def test_cambiar_estado_equipo_rechaza_valores_invalidos(self):
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

    def test_docente_staff_no_ve_reportes(self):
        self.client.force_login(self.crear_usuario('docstaff', Usuario.Rol.DOCENTE, is_staff=True))
        self.assertEqual(self.client.get('/reportes/').status_code, 302)

    def test_dias_invalido_usa_90(self):
        self.client.force_login(self.director)
        self.assertEqual(self.client.get('/reportes/', {'dias': 'abc'}).context['dias'], 90)

    def test_vencidos_muestran_al_estudiante_representado(self):
        inicio = timezone.now() - timedelta(days=3)
        s = self.crear_solicitud(self.docente, inicio=inicio, fin=inicio + timedelta(hours=1),
                                 estado=Solicitud.EstadoSolicitud.ENTREGADA)
        s.en_representacion_de = self.estudiante
        s.save()
        self.client.force_login(self.director)
        html = self.client.get('/reportes/').content.decode()
        self.assertIn('<th>Responsable</th>', html)
        self.assertIn('estudiante@inacapmail.cl', html)


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


class PanelAdminStaffNoSuperusuarioTests(LeicaTestCase):
    """El encargado de los tests es staff pero NO superusuario."""

    def setUp(self):
        self.otro_staff = self.crear_usuario('otrostaff', Usuario.Rol.CONTROL_CALIDAD, is_staff=True)
        self.client.force_login(self.encargado)

    def post(self, **data):
        return self.client.post('/panel-admin/', data)

    def test_no_resetea_ni_desactiva_a_otro_staff(self):
        self.post(accion='reset_password', user_id=self.otro_staff.id, nueva_password='tomado123')
        self.post(accion='toggle_activo', user_id=self.otro_staff.id)
        self.otro_staff.refresh_from_db()
        self.assertFalse(self.otro_staff.check_password('tomado123'))
        self.assertTrue(self.otro_staff.is_active)

    def test_no_asigna_roles_de_aprobacion(self):
        self.post(accion='cambiar_rol', user_id=self.estudiante.id, nuevo_rol='encargado_laboratorio')
        self.post(accion='crear_usuario', email='jefe@inacapmail.cl', rol='director_carrera', password='secreta123')
        self.estudiante.refresh_from_db()
        self.assertEqual(self.estudiante.rol, 'estudiante')
        self.assertFalse(Usuario.objects.filter(email='jefe@inacapmail.cl').exists())

    def test_no_se_quita_su_propia_sancion(self):
        Usuario.objects.filter(id=self.encargado.id).update(bloqueado_hasta=timezone.now() + timedelta(days=3))
        self.post(accion='desbloquear', user_id=self.encargado.id)
        self.encargado.refresh_from_db()
        self.assertTrue(self.encargado.esta_bloqueado())

    def test_superusuario_si_puede(self):
        admin = self.crear_usuario('admin', Usuario.Rol.ENCARGADO_LABORATORIO, is_staff=True, is_superuser=True)
        self.client.force_login(admin)
        self.post(accion='cambiar_rol', user_id=self.estudiante.id, nuevo_rol='encargado_laboratorio')
        self.post(accion='reset_password', user_id=self.otro_staff.id, nueva_password='NuevaClave1')
        self.estudiante.refresh_from_db()
        self.otro_staff.refresh_from_db()
        self.assertEqual(self.estudiante.rol, 'encargado_laboratorio')
        self.assertTrue(self.otro_staff.check_password('NuevaClave1'))

    def test_ids_no_numericos_no_dan_error_500(self):
        for data in ({'accion': 'toggle_activo', 'user_id': 'abc'},
                     {'accion': 'cambiar_estado_equipo', 'equipo_id': 'x', 'nuevo_estado': 'disponible'}):
            with self.subTest(data=data):
                self.assertEqual(self.post(**data).status_code, 302)
