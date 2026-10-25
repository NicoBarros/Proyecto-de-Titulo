"""
Flujo de solicitudes/prestamos: crear -> aprobar -> entregar -> devolver (RF-05 a RF-09).

Incluye regresiones de bugs ya corregidos (transiciones de estado, atomicidad,
bloqueo RF-09 y validacion de horario).
"""
from datetime import timedelta
from io import StringIO

from django.contrib.messages import get_messages
from django.core.management import call_command
from django.utils import timezone

from inventario.models import Bloqueo, Equipo, Insumo, Movimiento, Solicitud, Usuario

from .base import LeicaTestCase


def fmt(dt):
    return timezone.localtime(dt).strftime('%Y-%m-%dT%H:%M')


class CrearSolicitudTests(LeicaTestCase):

    def setUp(self):
        self.client.force_login(self.estudiante)
        self.inicio = timezone.now() + timedelta(days=1)
        self.fin = self.inicio + timedelta(hours=2)

    def post_solicitud(self, items, cantidades, **extra):
        data = {
            'item[]': items, 'cantidad[]': cantidades, 'lugar_uso': 'dentro_sede',
            'justificacion': 'clase', 'horario_inicio': fmt(self.inicio), 'horario_fin': fmt(self.fin),
        }
        data.update(extra)
        return self.client.post('/solicitudes/', data)

    def test_crea_kit_con_equipo_e_insumo(self):
        equipo = self.crear_equipo()
        insumo = self.crear_insumo(cantidad=10)
        r = self.post_solicitud([f'equipo:{equipo.id}', f'insumo:{insumo.id}'], ['1', '4'])
        self.assertRedirects(r, '/solicitudes/', fetch_redirect_response=False)
        s = Solicitud.objects.get()
        self.assertEqual(s.solicitante, self.estudiante)
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.PENDIENTE)
        self.assertEqual(s.items.count(), 2)
        self.assertEqual(s.items.get(insumo=insumo).cantidad, 4)

    def test_crear_no_descuenta_stock(self):
        insumo = self.crear_insumo(cantidad=10)
        self.post_solicitud([f'insumo:{insumo.id}'], ['4'])
        insumo.refresh_from_db()
        self.assertEqual(insumo.cantidad_disponible, 10)

    def test_equipo_no_disponible_rechaza_toda_la_solicitud(self):
        prestado = self.crear_equipo(estado=Equipo.Estado.PRESTADO)
        self.post_solicitud([f'equipo:{prestado.id}'], ['1'])
        self.assertFalse(Solicitud.objects.exists())

    def test_stock_insuficiente_hace_rollback(self):
        equipo = self.crear_equipo()
        insumo = self.crear_insumo(cantidad=2)
        self.post_solicitud([f'equipo:{equipo.id}', f'insumo:{insumo.id}'], ['1', '5'])
        self.assertFalse(Solicitud.objects.exists())

    def test_usuario_bloqueado_no_puede_solicitar(self):
        """RF-09: un usuario bloqueado no puede crear solicitudes."""
        self.estudiante.bloqueado_hasta = timezone.now() + timedelta(days=3)
        self.estudiante.save()
        self.post_solicitud([f'equipo:{self.crear_equipo().id}'], ['1'])
        self.assertFalse(Solicitud.objects.exists())

    def test_horario_fin_anterior_al_inicio_se_rechaza(self):
        self.fin = self.inicio - timedelta(hours=1)
        self.post_solicitud([f'equipo:{self.crear_equipo().id}'], ['1'])
        self.assertFalse(Solicitud.objects.exists())

    def test_no_se_repite_un_equipo_en_el_kit(self):
        e = self.crear_equipo()
        self.post_solicitud([f'equipo:{e.id}', f'equipo:{e.id}'], ['1', '1'])
        self.assertFalse(Solicitud.objects.exists())

    def test_stock_se_valida_sumando_filas_del_mismo_insumo(self):
        i = self.crear_insumo(cantidad=5)
        self.post_solicitud([f'insumo:{i.id}', f'insumo:{i.id}'], ['3', '3'])
        self.assertFalse(Solicitud.objects.exists())

    def test_filas_del_mismo_insumo_se_agrupan(self):
        i = self.crear_insumo(cantidad=10)
        self.post_solicitud([f'insumo:{i.id}', f'insumo:{i.id}'], ['3', '2'])
        self.assertEqual(Solicitud.objects.get().items.get().cantidad, 5)

    def test_cantidad_negativa_o_invalida_no_da_error_500(self):
        i = self.crear_insumo(cantidad=10)
        for cantidad in ('-3', '0', 'abc'):
            with self.subTest(cantidad=cantidad):
                r = self.post_solicitud([f'insumo:{i.id}'], [cantidad])
                self.assertEqual(r.status_code, 302)
        self.assertFalse(Solicitud.objects.exists())


class AprobarSolicitudTests(LeicaTestCase):

    def setUp(self):
        self.equipo = self.crear_equipo()
        self.client.force_login(self.encargado)

    def test_aprobar_registra_aprobador(self):
        s = self.crear_solicitud(self.estudiante, equipos=[self.equipo])
        self.accion_solicitud(s, 'aprobar')
        s.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.APROBADA)
        self.assertEqual(s.aprobado_por, self.encargado)
        self.assertIsNotNone(s.fecha_aprobacion)

    def test_director_puede_aprobar(self):
        s = self.crear_solicitud(self.estudiante, equipos=[self.equipo])
        self.client.force_login(self.director)
        self.accion_solicitud(s, 'aprobar')
        s.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.APROBADA)

    def test_choque_de_horario_impide_aprobar(self):
        inicio = timezone.now() + timedelta(days=1)
        self.crear_solicitud(self.docente, equipos=[self.equipo], inicio=inicio,
                             fin=inicio + timedelta(hours=2), estado=Solicitud.EstadoSolicitud.APROBADA)
        s = self.crear_solicitud(self.estudiante, equipos=[self.equipo],
                                 inicio=inicio + timedelta(hours=1), fin=inicio + timedelta(hours=3))
        self.accion_solicitud(s, 'aprobar')
        s.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.PENDIENTE)

    def test_horarios_contiguos_no_chocan(self):
        inicio = timezone.now() + timedelta(days=1)
        self.crear_solicitud(self.docente, equipos=[self.equipo], inicio=inicio,
                             fin=inicio + timedelta(hours=2), estado=Solicitud.EstadoSolicitud.APROBADA)
        s = self.crear_solicitud(self.estudiante, equipos=[self.equipo],
                                 inicio=inicio + timedelta(hours=2), fin=inicio + timedelta(hours=4))
        self.accion_solicitud(s, 'aprobar')
        s.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.APROBADA)

    def test_rechazar(self):
        s = self.crear_solicitud(self.estudiante, equipos=[self.equipo])
        self.accion_solicitud(s, 'rechazar')
        s.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.RECHAZADA)


class EntregaDevolucionTests(LeicaTestCase):

    def setUp(self):
        self.equipo = self.crear_equipo()
        self.renovable = self.crear_insumo('Cables', cantidad=10, tipo=Insumo.Tipo.RENOVABLE)
        self.perecible = self.crear_insumo('Resistencias', cantidad=100, tipo=Insumo.Tipo.PERECIBLE)
        self.client.force_login(self.encargado)

    def solicitud_aprobada(self, **kw):
        kw.setdefault('equipos', [self.equipo])
        kw.setdefault('insumos', [(self.renovable, 3), (self.perecible, 20)])
        return self.crear_solicitud(self.estudiante, estado=Solicitud.EstadoSolicitud.APROBADA, **kw)

    def test_entregar_presta_equipo_y_descuenta_stock(self):
        s = self.solicitud_aprobada()
        self.accion_solicitud(s, 'entregar')
        s.refresh_from_db()
        self.equipo.refresh_from_db()
        self.renovable.refresh_from_db()
        self.perecible.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.ENTREGADA)
        self.assertEqual(self.equipo.estado, Equipo.Estado.PRESTADO)
        self.assertEqual(self.renovable.cantidad_disponible, 7)
        self.assertEqual(self.perecible.cantidad_disponible, 80)
        self.assertTrue(Movimiento.objects.filter(solicitud=s, tipo='entrega', responsable=self.encargado).exists())

    def test_devolver_a_tiempo_repone_solo_renovables(self):
        s = self.solicitud_aprobada()
        self.accion_solicitud(s, 'entregar')
        self.accion_solicitud(s, 'devolver', estado_equipo='bueno')
        s.refresh_from_db()
        self.equipo.refresh_from_db()
        self.renovable.refresh_from_db()
        self.perecible.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.DEVUELTA)
        self.assertEqual(self.equipo.estado, Equipo.Estado.DISPONIBLE)
        self.assertEqual(self.renovable.cantidad_disponible, 10)
        self.assertEqual(self.perecible.cantidad_disponible, 80)
        self.assertFalse(Bloqueo.objects.exists())

    def test_devolver_danado_envia_a_mantenimiento(self):
        s = self.solicitud_aprobada(insumos=[])
        self.accion_solicitud(s, 'entregar')
        self.accion_solicitud(s, 'devolver', estado_equipo='dañado')
        self.equipo.refresh_from_db()
        self.assertEqual(self.equipo.estado, Equipo.Estado.EN_MANTENIMIENTO)
        self.assertEqual(Movimiento.objects.get(tipo='devolucion').estado_equipo, 'dañado')

    def test_devolucion_atrasada_bloquea_7_dias(self):
        inicio = timezone.now() - timedelta(days=2)
        s = self.solicitud_aprobada(insumos=[], inicio=inicio, fin=inicio + timedelta(hours=2))
        self.accion_solicitud(s, 'entregar')
        self.accion_solicitud(s, 'devolver')
        s.refresh_from_db()
        self.estudiante.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.DEVUELTA_ATRASO)
        self.assertTrue(self.estudiante.esta_bloqueado())
        restante = self.estudiante.bloqueado_hasta - timezone.now()
        self.assertTrue(timedelta(days=6, hours=23) < restante <= timedelta(days=7))
        bloqueo = Bloqueo.objects.get()
        self.assertEqual((bloqueo.usuario, bloqueo.seccion, bloqueo.solicitud), (self.estudiante, 'TIN-401', s))

    def test_atraso_bloquea_al_representado(self):
        inicio = timezone.now() - timedelta(days=2)
        s = self.crear_solicitud(self.docente, equipos=[self.equipo], inicio=inicio,
                                 fin=inicio + timedelta(hours=1), estado=Solicitud.EstadoSolicitud.ENTREGADA)
        s.en_representacion_de = self.estudiante
        s.save()
        self.accion_solicitud(s, 'devolver')
        self.estudiante.refresh_from_db()
        self.docente.refresh_from_db()
        self.assertTrue(self.estudiante.esta_bloqueado())
        self.assertFalse(self.docente.esta_bloqueado())

    def test_no_se_entrega_sin_aprobacion(self):
        """Las acciones validan el estado actual de la solicitud."""
        s = self.crear_solicitud(self.estudiante, equipos=[self.equipo])
        self.accion_solicitud(s, 'entregar')
        s.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.PENDIENTE)

    def test_devolver_dos_veces_no_duplica_stock(self):
        s = self.solicitud_aprobada(equipos=[], insumos=[(self.renovable, 3)])
        self.accion_solicitud(s, 'entregar')
        self.accion_solicitud(s, 'devolver')
        self.accion_solicitud(s, 'devolver')
        self.renovable.refresh_from_db()
        self.assertEqual(self.renovable.cantidad_disponible, 10)

    def test_entrega_fallida_no_deja_cambios_a_medias(self):
        """'entregar' es atomica: si falla un insumo, el equipo no queda PRESTADO."""
        s = self.solicitud_aprobada(insumos=[(self.renovable, 3)])
        Insumo.objects.filter(id=self.renovable.id).update(cantidad_disponible=1)
        self.accion_solicitud(s, 'entregar')
        self.equipo.refresh_from_db()
        self.assertEqual(self.equipo.estado, Equipo.Estado.DISPONIBLE)
        s.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.APROBADA)
        self.assertFalse(Movimiento.objects.exists())

    def test_no_se_devuelve_una_solicitud_pendiente(self):
        s = self.crear_solicitud(self.estudiante, insumos=[(self.renovable, 3)])
        self.accion_solicitud(s, 'devolver')
        self.renovable.refresh_from_db()
        self.assertEqual(self.renovable.cantidad_disponible, 10)

    def test_no_se_rechaza_una_solicitud_entregada(self):
        s = self.solicitud_aprobada(insumos=[])
        self.accion_solicitud(s, 'entregar')
        self.accion_solicitud(s, 'rechazar')
        s.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.ENTREGADA)

    def test_no_se_entrega_equipo_que_ya_esta_prestado(self):
        s = self.solicitud_aprobada(insumos=[])
        Equipo.objects.filter(id=self.equipo.id).update(estado=Equipo.Estado.PRESTADO)
        self.accion_solicitud(s, 'entregar')
        s.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.APROBADA)

    def test_accion_desconocida(self):
        s = self.solicitud_aprobada()
        r = self.client.post('/solicitudes/', {'solicitud_id': s.id, 'accion': 'borrar'}, follow=True)
        textos = [str(m) for m in get_messages(r.wsgi_request)]
        self.assertEqual(textos, ['Acción no válida.'])

    def test_estado_de_devolucion_invalido(self):
        s = self.solicitud_aprobada(insumos=[])
        self.accion_solicitud(s, 'entregar')
        self.accion_solicitud(s, 'devolver', estado_equipo='Dañado!!')
        s.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.ENTREGADA)

    def test_devolucion_respeta_equipo_dado_de_baja_mientras_estaba_prestado(self):
        s = self.solicitud_aprobada(insumos=[])
        self.accion_solicitud(s, 'entregar')
        Equipo.objects.filter(id=self.equipo.id).update(estado=Equipo.Estado.FUERA_SERVICIO)
        self.accion_solicitud(s, 'devolver', estado_equipo='bueno')
        self.equipo.refresh_from_db()
        self.assertEqual(self.equipo.estado, Equipo.Estado.FUERA_SERVICIO)

    def test_no_se_aprueba_con_equipo_en_mantenimiento(self):
        s = self.crear_solicitud(self.estudiante, equipos=[self.equipo])
        Equipo.objects.filter(id=self.equipo.id).update(estado=Equipo.Estado.EN_MANTENIMIENTO)
        self.accion_solicitud(s, 'aprobar')
        s.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.PENDIENTE)

    def test_solicitud_aprobada_ofrece_rechazar_y_devolucion_usa_select(self):
        aprobada = self.solicitud_aprobada(insumos=[])
        html = self.client.get('/solicitudes/').content.decode()
        self.assertIn('value="rechazar"', html)
        self.accion_solicitud(aprobada, 'entregar')
        html = self.client.get('/solicitudes/').content.decode()
        self.assertIn('<select name="estado_item_', html)
        self.assertNotIn('prompt(', html)


class VisibilidadSolicitudesTests(LeicaTestCase):

    def test_estudiante_solo_ve_sus_solicitudes(self):
        propia = self.crear_solicitud(self.estudiante)
        ajena = self.crear_solicitud(self.docente)
        self.client.force_login(self.estudiante)
        self.assertEqual(list(self.client.get('/solicitudes/').context['solicitudes']), [propia])
        self.client.force_login(self.encargado)
        self.assertEqual(set(self.client.get('/solicitudes/').context['solicitudes']), {propia, ajena})


class AtrasosAutomaticosTests(LeicaTestCase):

    def setUp(self):
        self.equipo = self.crear_equipo(estado=Equipo.Estado.PRESTADO)
        inicio = timezone.now() - timedelta(days=2)
        self.vencida = self.crear_solicitud(self.estudiante, equipos=[self.equipo], inicio=inicio,
                                            fin=inicio + timedelta(hours=3), estado=Solicitud.EstadoSolicitud.ENTREGADA)
        self.vigente = self.crear_solicitud(self.docente, estado=Solicitud.EstadoSolicitud.ENTREGADA)

    def test_al_abrir_el_dashboard_se_marcan_las_vencidas(self):
        self.client.force_login(self.estudiante)
        self.client.get('/')
        self.vencida.refresh_from_db()
        self.vigente.refresh_from_db()
        self.assertEqual(self.vencida.estado, Solicitud.EstadoSolicitud.ATRASADA)
        self.assertEqual(self.vigente.estado, Solicitud.EstadoSolicitud.ENTREGADA)

    def test_dashboard_cuenta_y_alerta_solo_a_aprobadores(self):
        self.client.force_login(self.encargado)
        r = self.client.get('/')
        self.assertEqual(r.context['totales']['solicitudes_atrasadas'], 1)
        self.assertEqual(list(r.context['atrasadas']), [self.vencida])
        self.assertContains(r, 'Préstamos vencidos sin devolver (1)')
        self.client.force_login(self.estudiante)
        self.assertNotContains(self.client.get('/'), 'Préstamos vencidos sin devolver')

    def test_solicitud_atrasada_se_puede_devolver(self):
        self.client.force_login(self.encargado)
        self.client.get('/solicitudes/')
        self.accion_solicitud(self.vencida, 'devolver', estado_equipo='bueno')
        self.vencida.refresh_from_db()
        self.equipo.refresh_from_db()
        self.estudiante.refresh_from_db()
        self.assertEqual(self.vencida.estado, Solicitud.EstadoSolicitud.DEVUELTA_ATRASO)
        self.assertEqual(self.equipo.estado, Equipo.Estado.DISPONIBLE)
        self.assertTrue(self.estudiante.esta_bloqueado())

    def test_pantalla_muestra_vencimiento_y_boton_devolver(self):
        self.client.force_login(self.encargado)
        html = self.client.get('/solicitudes/').content.decode()
        self.assertIn('Vencida hace', html)
        self.assertIn('value="devolver"', html)

    def test_equipo_atrasado_cuenta_como_reservado_al_aprobar(self):
        Solicitud.marcar_atrasadas()
        ahora = timezone.now()
        otra = self.crear_solicitud(self.docente, equipos=[self.equipo],
                                    inicio=ahora - timedelta(days=2), fin=ahora - timedelta(days=1, hours=22))
        self.client.force_login(self.encargado)
        self.accion_solicitud(otra, 'aprobar')
        otra.refresh_from_db()
        self.assertEqual(otra.estado, Solicitud.EstadoSolicitud.PENDIENTE)

    def test_reportes_lista_las_atrasadas(self):
        self.client.force_login(self.director)
        self.assertEqual(list(self.client.get('/reportes/').context['vencidos']), [self.vencida])

    def test_comando_marcar_atrasadas(self):
        salida = StringIO()
        call_command('marcar_atrasadas', stdout=salida)
        self.assertIn('Solicitudes marcadas como atrasadas: 1', salida.getvalue())
        self.vencida.refresh_from_db()
        self.assertEqual(self.vencida.estado, Solicitud.EstadoSolicitud.ATRASADA)


class RepresentacionTests(LeicaTestCase):

    def post_solicitud(self, usuario, representado_id, equipo=None):
        equipo = equipo or self.crear_equipo()
        inicio = timezone.now() + timedelta(days=1)
        self.client.force_login(usuario)
        return self.client.post('/solicitudes/', {
            'item[]': [f'equipo:{equipo.id}'], 'cantidad[]': ['1'], 'lugar_uso': 'dentro_sede',
            'horario_inicio': fmt(inicio), 'horario_fin': fmt(inicio + timedelta(hours=2)),
            'en_representacion_de': representado_id,
        })

    def test_docente_solicita_en_representacion_de_estudiante(self):
        self.post_solicitud(self.docente, self.estudiante.id)
        s = Solicitud.objects.get()
        self.assertEqual((s.solicitante, s.en_representacion_de), (self.docente, self.estudiante))

    def test_estudiante_ve_la_solicitud_hecha_a_su_nombre(self):
        self.post_solicitud(self.docente, self.estudiante.id)
        self.client.force_login(self.estudiante)
        r = self.client.get('/solicitudes/')
        self.assertEqual(len(r.context['solicitudes']), 1)
        self.assertContains(r, 'en representación de')

    def test_estudiante_no_puede_representar(self):
        otro = self.crear_usuario('est2', Usuario.Rol.ESTUDIANTE)
        self.post_solicitud(self.estudiante, otro.id)
        self.assertFalse(Solicitud.objects.exists())

    def test_solo_se_representa_a_estudiantes_activos(self):
        inactivo = self.crear_usuario('inactivo', Usuario.Rol.ESTUDIANTE, is_active=False)
        equipo = self.crear_equipo()
        for representado in (self.director.id, inactivo.id, 'abc'):
            with self.subTest(representado=representado):
                self.post_solicitud(self.docente, representado, equipo)
        self.assertFalse(Solicitud.objects.exists())

    def test_no_se_representa_a_un_estudiante_bloqueado(self):
        self.estudiante.bloqueado_hasta = timezone.now() + timedelta(days=2)
        self.estudiante.save()
        self.post_solicitud(self.docente, self.estudiante.id)
        self.assertFalse(Solicitud.objects.exists())

    def test_formulario_ofrece_estudiantes_solo_a_quien_puede_representar(self):
        self.client.force_login(self.docente)
        self.assertContains(self.client.get('/solicitudes/'), 'name="en_representacion_de"')
        self.client.force_login(self.estudiante)
        self.assertNotContains(self.client.get('/solicitudes/'), 'name="en_representacion_de"')
