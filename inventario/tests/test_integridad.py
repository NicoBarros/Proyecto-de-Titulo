from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from inventario.models import Equipo, EventoSeguridad, Insumo, Mantenimiento, Solicitud, Usuario

from .base import LeicaTestCase


def fmt(dt):
    return timezone.localtime(dt).strftime('%Y-%m-%dT%H:%M')


class MantenimientoIntegridadTests(LeicaTestCase):

    def setUp(self):
        self.client.force_login(self.encargado)

    def diagnosticar(self, equipo, costo='100'):
        return self.client.post('/mantenimiento/', {
            'equipo_id': equipo.id, 'falla_descrita': 'No enciende', 'costo_cotizado': costo,
        })

    def resolver(self, mant, accion):
        return self.client.post('/mantenimiento/', {'mant_id': mant.id, 'accion_mant': accion})

    def test_costo_muy_superior_al_valor_no_da_error(self):
        e = self.crear_equipo(valor=Decimal('1000'))
        r = self.diagnosticar(e, '50000')
        self.assertEqual(r.status_code, 302)
        m = Mantenimiento.objects.get()
        self.assertEqual(m.porcentaje_costo, Decimal('50.0000'))
        self.assertEqual(m.decision, Mantenimiento.Decision.DAR_BAJA)

    def test_costo_negativo_rechazado(self):
        e = self.crear_equipo()
        self.diagnosticar(e, '-10')
        self.assertFalse(Mantenimiento.objects.exists())

    def test_no_diagnostica_equipo_prestado(self):
        e = self.crear_equipo(estado=Equipo.Estado.PRESTADO)
        self.diagnosticar(e)
        self.assertFalse(Mantenimiento.objects.exists())
        e.refresh_from_db()
        self.assertEqual(e.estado, Equipo.Estado.PRESTADO)

    def test_no_diagnostica_equipo_fuera_de_servicio(self):
        e = self.crear_equipo(estado=Equipo.Estado.FUERA_SERVICIO)
        self.diagnosticar(e)
        self.assertFalse(Mantenimiento.objects.exists())

    def test_no_abre_dos_mantenimientos_del_mismo_equipo(self):
        e = self.crear_equipo()
        self.diagnosticar(e)
        self.diagnosticar(e)
        self.assertEqual(Mantenimiento.objects.count(), 1)

    def test_diagnostica_equipo_devuelto_danado_sin_mantenimiento(self):
        e = self.crear_equipo(estado=Equipo.Estado.EN_MANTENIMIENTO)
        self.diagnosticar(e)
        self.assertEqual(Mantenimiento.objects.count(), 1)

    def test_sugerencia_dar_baja_queda_abierta_y_se_puede_reparar(self):
        e = self.crear_equipo(valor=Decimal('1000'))
        self.diagnosticar(e, '900')
        m = Mantenimiento.objects.get()
        self.assertIsNone(m.fecha_resolucion)
        self.resolver(m, 'reparar')
        self.resolver(m, 'completar_reparacion')
        m.refresh_from_db()
        e.refresh_from_db()
        self.assertEqual(m.decision, Mantenimiento.Decision.COMPLETADO)
        self.assertEqual(e.estado, Equipo.Estado.DISPONIBLE)

    def test_reparar_no_cierra_el_mantenimiento(self):
        e = self.crear_equipo(estado=Equipo.Estado.EN_MANTENIMIENTO)
        m = Mantenimiento.objects.create(equipo=e)
        self.resolver(m, 'reparar')
        m.refresh_from_db()
        self.assertIsNone(m.fecha_resolucion)

    def test_no_completa_mantenimiento_dado_de_baja(self):
        e = self.crear_equipo(estado=Equipo.Estado.EN_MANTENIMIENTO)
        m = Mantenimiento.objects.create(equipo=e)
        self.resolver(m, 'dar_baja')
        self.resolver(m, 'completar_reparacion')
        m.refresh_from_db()
        e.refresh_from_db()
        self.assertEqual(m.decision, Mantenimiento.Decision.DAR_BAJA)
        self.assertEqual(e.estado, Equipo.Estado.FUERA_SERVICIO)

    def test_accion_invalida_no_modifica(self):
        e = self.crear_equipo(estado=Equipo.Estado.EN_MANTENIMIENTO)
        m = Mantenimiento.objects.create(equipo=e)
        self.resolver(m, 'inventada')
        m.refresh_from_db()
        self.assertEqual(m.decision, Mantenimiento.Decision.PENDIENTE)

    def test_selector_excluye_prestados_y_con_mantenimiento_abierto(self):
        libre = self.crear_equipo('A-1')
        self.crear_equipo('A-2', estado=Equipo.Estado.PRESTADO)
        ocupado = self.crear_equipo('A-3', estado=Equipo.Estado.EN_MANTENIMIENTO)
        Mantenimiento.objects.create(equipo=ocupado)
        r = self.client.get('/mantenimiento/')
        self.assertEqual(list(r.context['equipos']), [libre])


class InsumoEdicionTests(LeicaTestCase):

    def setUp(self):
        self.client.force_login(self.encargado)
        self.insumo = self.crear_insumo(cantidad=10)
        Insumo.objects.filter(id=self.insumo.id).update(cantidad_disponible=7)

    def editar(self, total):
        return self.client.post(f'/inventario/insumo/{self.insumo.id}/editar/', {
            'nombre': 'Protoboard', 'tipo': 'renovable', 'cantidad_total': total, 'umbral_minimo': '2',
        })

    def test_aumentar_total_aumenta_disponible(self):
        self.editar('15')
        self.insumo.refresh_from_db()
        self.assertEqual((self.insumo.cantidad_total, self.insumo.cantidad_disponible), (15, 12))

    def test_reducir_total_reduce_disponible(self):
        self.editar('5')
        self.insumo.refresh_from_db()
        self.assertEqual((self.insumo.cantidad_total, self.insumo.cantidad_disponible), (5, 2))

    def test_total_menor_a_lo_entregado_se_rechaza(self):
        r = self.editar('2')
        self.assertEqual(r.status_code, 200)
        self.insumo.refresh_from_db()
        self.assertEqual((self.insumo.cantidad_total, self.insumo.cantidad_disponible), (10, 7))


class ReportesParametrosTests(LeicaTestCase):

    def test_dias_enorme_no_da_error(self):
        self.client.force_login(self.encargado)
        r = self.client.get('/reportes/', {'dias': '99999999999'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['dias'], 3650)


class PanelEstadoEquipoTests(LeicaTestCase):

    def setUp(self):
        self.client.force_login(self.encargado)

    def cambiar(self, equipo, estado):
        self.client.post('/panel-admin/', {'accion': 'cambiar_estado_equipo', 'equipo_id': equipo.id, 'nuevo_estado': estado})
        equipo.refresh_from_db()

    def test_no_libera_equipo_prestado(self):
        e = self.crear_equipo(estado=Equipo.Estado.PRESTADO)
        self.cambiar(e, 'disponible')
        self.assertEqual(e.estado, Equipo.Estado.PRESTADO)

    def test_no_marca_prestado_manualmente(self):
        e = self.crear_equipo()
        self.cambiar(e, 'prestado')
        self.assertEqual(e.estado, Equipo.Estado.DISPONIBLE)


class PanelCuentasTests(LeicaTestCase):

    def setUp(self):
        self.client.force_login(self.encargado)

    def post(self, **data):
        return self.client.post('/panel-admin/', data)

    def test_crear_usuario_aplica_validadores_de_password(self):
        for clave in ('abc1234', '12345678', 'password'):
            self.post(accion='crear_usuario', email='nuevo@inacapmail.cl', rol='docente', password=clave)
        self.assertFalse(Usuario.objects.filter(email='nuevo@inacapmail.cl').exists())

    def test_reset_password_aplica_validadores(self):
        self.post(accion='reset_password', user_id=self.docente.id, nueva_password='12345678')
        self.docente.refresh_from_db()
        self.assertFalse(self.docente.check_password('12345678'))

    def test_cambios_de_cuenta_quedan_registrados(self):
        self.post(accion='cambiar_rol', user_id=self.estudiante.id, nuevo_rol='docente')
        self.post(accion='toggle_activo', user_id=self.estudiante.id)
        self.post(accion='desbloquear', user_id=self.estudiante.id)
        self.post(accion='reset_password', user_id=self.estudiante.id, nueva_password='NuevaClave2026')
        eventos = EventoSeguridad.objects.filter(tipo=EventoSeguridad.Tipo.CAMBIO_CUENTA).order_by('id')
        self.assertEqual(eventos.count(), 4)
        self.assertTrue(all(e.usuario == self.encargado for e in eventos))
        self.assertIn('estudiante@inacapmail.cl: rol Estudiante → Docente', eventos[0].detalle)


class AtrasosYSancionesTests(LeicaTestCase):

    def post_solicitud(self, equipo, **extra):
        inicio = timezone.now() + timedelta(days=1)
        return self.client.post('/solicitudes/', {
            'item[]': [f'equipo:{equipo.id}'], 'cantidad[]': ['1'], 'lugar_uso': 'dentro_sede',
            'horario_inicio': fmt(inicio), 'horario_fin': fmt(inicio + timedelta(hours=2)), **extra,
        })

    def crear_atrasada(self, solicitante, **extra):
        inicio = timezone.now() - timedelta(days=2)
        s = self.crear_solicitud(solicitante, inicio=inicio, fin=inicio + timedelta(hours=2),
                                 estado=Solicitud.EstadoSolicitud.ATRASADA)
        Solicitud.objects.filter(id=s.id).update(**extra)
        return s

    def test_con_atraso_pendiente_no_puede_solicitar(self):
        self.crear_atrasada(self.estudiante)
        self.client.force_login(self.estudiante)
        self.post_solicitud(self.crear_equipo())
        self.assertEqual(Solicitud.objects.count(), 1)

    def test_entregada_vencida_tambien_bloquea(self):
        inicio = timezone.now() - timedelta(days=2)
        self.crear_solicitud(self.estudiante, inicio=inicio, fin=inicio + timedelta(hours=2),
                             estado=Solicitud.EstadoSolicitud.ENTREGADA)
        self.client.force_login(self.estudiante)
        self.post_solicitud(self.crear_equipo())
        self.assertEqual(Solicitud.objects.count(), 1)

    def test_docente_no_representa_a_estudiante_con_atraso(self):
        self.crear_atrasada(self.docente, en_representacion_de=self.estudiante)
        self.client.force_login(self.docente)
        self.post_solicitud(self.crear_equipo(), en_representacion_de=self.estudiante.id)
        self.assertEqual(Solicitud.objects.count(), 1)

    def test_atraso_del_representado_no_bloquea_al_docente(self):
        self.crear_atrasada(self.docente, en_representacion_de=self.estudiante)
        self.client.force_login(self.docente)
        self.post_solicitud(self.crear_equipo())
        self.assertEqual(Solicitud.objects.count(), 2)

    def test_devolucion_atrasada_no_acorta_sancion_mayor(self):
        hasta = timezone.now() + timedelta(days=30)
        Usuario.objects.filter(id=self.estudiante.id).update(bloqueado_hasta=hasta)
        equipo = self.crear_equipo(estado=Equipo.Estado.PRESTADO)
        inicio = timezone.now() - timedelta(days=2)
        s = self.crear_solicitud(self.estudiante, equipos=[equipo], inicio=inicio, fin=inicio + timedelta(hours=2),
                                 estado=Solicitud.EstadoSolicitud.ATRASADA)
        self.client.force_login(self.encargado)
        self.accion_solicitud(s, 'devolver')
        self.estudiante.refresh_from_db()
        self.assertEqual(self.estudiante.bloqueado_hasta, hasta)


class CancelarSolicitudTests(LeicaTestCase):

    def cancelar(self, usuario, solicitud):
        self.client.force_login(usuario)
        self.accion_solicitud(solicitud, 'cancelar')
        solicitud.refresh_from_db()

    def test_solicitante_cancela_pendiente(self):
        s = self.crear_solicitud(self.estudiante, equipos=[self.crear_equipo()])
        self.cancelar(self.estudiante, s)
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.CANCELADA)

    def test_solicitante_cancela_aprobada(self):
        s = self.crear_solicitud(self.estudiante, estado=Solicitud.EstadoSolicitud.APROBADA)
        self.cancelar(self.estudiante, s)
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.CANCELADA)

    def test_otro_usuario_no_cancela(self):
        s = self.crear_solicitud(self.estudiante)
        self.cancelar(self.crear_usuario('otro', Usuario.Rol.ESTUDIANTE), s)
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.PENDIENTE)

    def test_aprobador_no_cancela_solicitud_ajena(self):
        s = self.crear_solicitud(self.estudiante)
        self.cancelar(self.encargado, s)
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.PENDIENTE)

    def test_no_cancela_entregada(self):
        s = self.crear_solicitud(self.estudiante, estado=Solicitud.EstadoSolicitud.ENTREGADA)
        self.cancelar(self.estudiante, s)
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.ENTREGADA)

    def test_cancelada_libera_el_horario(self):
        equipo = self.crear_equipo()
        s = self.crear_solicitud(self.estudiante, equipos=[equipo], estado=Solicitud.EstadoSolicitud.APROBADA)
        self.cancelar(self.estudiante, s)
        otra = self.crear_solicitud(self.docente, equipos=[equipo], inicio=s.horario_inicio, fin=s.horario_fin)
        self.client.force_login(self.encargado)
        self.accion_solicitud(otra, 'aprobar')
        otra.refresh_from_db()
        self.assertEqual(otra.estado, Solicitud.EstadoSolicitud.APROBADA)
