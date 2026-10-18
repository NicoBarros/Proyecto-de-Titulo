"""
Flujo de solicitudes/prestamos: crear -> aprobar -> entregar -> devolver (RF-05 a RF-09).

Los tests marcados con @expectedFailure documentan BUGS CONOCIDOS: describen el
comportamiento correcto y hoy fallan. Cuando se corrija el bug, Django los
reportara como "unexpected success" y hay que quitarles el decorador.
"""
from datetime import timedelta
from unittest import expectedFailure

from django.utils import timezone

from inventario.models import Equipo, Insumo, Solicitud, Movimiento, Bloqueo
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

    @expectedFailure
    def test_bug_usuario_bloqueado_no_deberia_poder_solicitar(self):
        """RF-09: el bloqueo (bloqueado_hasta) no se valida al crear la solicitud."""
        self.estudiante.bloqueado_hasta = timezone.now() + timedelta(days=3)
        self.estudiante.save()
        self.post_solicitud([f'equipo:{self.crear_equipo().id}'], ['1'])
        self.assertFalse(Solicitud.objects.exists())

    @expectedFailure
    def test_bug_horario_fin_anterior_al_inicio_deberia_rechazarse(self):
        self.fin = self.inicio - timedelta(hours=1)
        self.post_solicitud([f'equipo:{self.crear_equipo().id}'], ['1'])
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
        s.refresh_from_db(); self.equipo.refresh_from_db()
        self.renovable.refresh_from_db(); self.perecible.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.ENTREGADA)
        self.assertEqual(self.equipo.estado, Equipo.Estado.PRESTADO)
        self.assertEqual(self.renovable.cantidad_disponible, 7)
        self.assertEqual(self.perecible.cantidad_disponible, 80)
        self.assertTrue(Movimiento.objects.filter(solicitud=s, tipo='entrega', responsable=self.encargado).exists())

    def test_devolver_a_tiempo_repone_solo_renovables(self):
        s = self.solicitud_aprobada()
        self.accion_solicitud(s, 'entregar')
        self.accion_solicitud(s, 'devolver', estado_equipo='bueno')
        s.refresh_from_db(); self.equipo.refresh_from_db()
        self.renovable.refresh_from_db(); self.perecible.refresh_from_db()
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
        s.refresh_from_db(); self.estudiante.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.ATRASADA)
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
        self.estudiante.refresh_from_db(); self.docente.refresh_from_db()
        self.assertTrue(self.estudiante.esta_bloqueado())
        self.assertFalse(self.docente.esta_bloqueado())

    @expectedFailure
    def test_bug_no_deberia_entregarse_sin_aprobacion(self):
        """Las acciones no validan el estado actual: se puede 'entregar' una solicitud PENDIENTE."""
        s = self.crear_solicitud(self.estudiante, equipos=[self.equipo])
        self.accion_solicitud(s, 'entregar')
        s.refresh_from_db()
        self.assertEqual(s.estado, Solicitud.EstadoSolicitud.PENDIENTE)

    @expectedFailure
    def test_bug_devolver_dos_veces_duplica_stock(self):
        s = self.solicitud_aprobada(equipos=[], insumos=[(self.renovable, 3)])
        self.accion_solicitud(s, 'entregar')
        self.accion_solicitud(s, 'devolver')
        self.accion_solicitud(s, 'devolver')
        self.renovable.refresh_from_db()
        self.assertEqual(self.renovable.cantidad_disponible, 10)

    @expectedFailure
    def test_bug_entrega_fallida_deja_cambios_a_medias(self):
        """'entregar' no usa transaction.atomic: si falla un insumo, el equipo queda PRESTADO igual."""
        s = self.solicitud_aprobada(insumos=[(self.renovable, 3)])
        Insumo.objects.filter(id=self.renovable.id).update(cantidad_disponible=1)
        self.accion_solicitud(s, 'entregar')
        self.equipo.refresh_from_db()
        self.assertEqual(self.equipo.estado, Equipo.Estado.DISPONIBLE)
