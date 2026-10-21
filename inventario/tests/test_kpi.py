from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from inventario.kpi import calcular_kpis
from inventario.models import Equipo, Mantenimiento, Movimiento, Solicitud
from .base import LeicaTestCase


class KpiTests(LeicaTestCase):

    def kpis(self, dias=30):
        return {k.clave: k for k in calcular_kpis(dias)}

    def solicitud_con_fechas(self, creada, aprobada=None, estado=Solicitud.EstadoSolicitud.APROBADA, equipos=()):
        s = self.crear_solicitud(self.estudiante, equipos=equipos, estado=estado)
        Solicitud.objects.filter(id=s.id).update(created_at=creada, fecha_aprobacion=aprobada)
        return s

    def movimiento(self, solicitud, tipo, fecha):
        m = Movimiento.objects.create(solicitud=solicitud, tipo=tipo, responsable=self.encargado)
        Movimiento.objects.filter(id=m.id).update(fecha=fecha)

    def test_sin_datos(self):
        k = self.kpis()
        for clave in ('aprobacion_horas', 'devoluciones_a_tiempo', 'disponibilidad', 'uso_equipos',
                      'stock_critico', 'reparacion_dias'):
            with self.subTest(clave=clave):
                self.assertIsNone(k[clave].cumple)
                self.assertEqual(k[clave].texto, 'Sin datos')
        self.assertEqual((k['atrasos_activos'].texto, k['atrasos_activos'].cumple), ('0', True))

    def test_tiempo_promedio_de_aprobacion(self):
        ahora = timezone.now()
        self.solicitud_con_fechas(ahora - timedelta(days=3), ahora - timedelta(days=3) + timedelta(hours=10))
        self.solicitud_con_fechas(ahora - timedelta(days=2), ahora - timedelta(days=2) + timedelta(hours=50))
        self.solicitud_con_fechas(ahora - timedelta(days=60), ahora - timedelta(days=59))
        k = self.kpis()['aprobacion_horas']
        self.assertAlmostEqual(k.valor, 30)
        self.assertEqual((k.texto, k.objetivo, k.cumple), ('30 h', '≤ 24 h', False))
        self.assertEqual(k.detalle, '2 solicitudes aprobadas')

    def test_devoluciones_a_tiempo(self):
        ahora = timezone.now()
        for estado in ['devuelta', 'devuelta', 'devuelta', 'devuelta_atraso']:
            s = self.crear_solicitud(self.estudiante, estado=estado)
            self.movimiento(s, Movimiento.TipoMovimiento.DEVOLUCION, ahora - timedelta(days=1))
        vieja = self.crear_solicitud(self.estudiante, estado='devuelta_atraso')
        self.movimiento(vieja, Movimiento.TipoMovimiento.DEVOLUCION, ahora - timedelta(days=100))
        k = self.kpis()['devoluciones_a_tiempo']
        self.assertEqual((k.texto, k.cumple), ('75 %', False))
        self.assertTrue(self.kpis(365)['devoluciones_a_tiempo'].valor < 75)

    def test_disponibilidad_excluye_equipos_dados_de_baja(self):
        for i, estado in enumerate(['disponible', 'disponible', 'disponible', 'prestado', 'fuera_servicio']):
            self.crear_equipo(f'D-{i}', estado=estado)
        k = self.kpis()['disponibilidad']
        self.assertEqual((k.texto, k.cumple), ('75 %', True))
        self.assertEqual(k.detalle, '3 de 4 equipos operativos')

    def test_tasa_de_uso(self):
        usado, _, _, _ = [self.crear_equipo(f'U-{i}') for i in range(4)]
        s = self.crear_solicitud(self.estudiante, equipos=[usado], estado='devuelta')
        self.movimiento(s, Movimiento.TipoMovimiento.ENTREGA, timezone.now() - timedelta(days=5))
        k = self.kpis()['uso_equipos']
        self.assertEqual((k.texto, k.cumple), ('25 %', False))
        self.assertEqual(self.kpis(7)['uso_equipos'].valor, 25)

    def test_atrasos_activos_marca_vencidas(self):
        inicio = timezone.now() - timedelta(days=2)
        self.crear_solicitud(self.estudiante, inicio=inicio, fin=inicio + timedelta(hours=1),
                             estado=Solicitud.EstadoSolicitud.ENTREGADA)
        k = self.kpis()['atrasos_activos']
        self.assertEqual((k.texto, k.cumple), ('1', False))

    def test_stock_critico(self):
        for i in range(9):
            self.crear_insumo(f'Insumo {i}', cantidad=10, umbral=2)
        self.crear_insumo('Critico', cantidad=10, umbral=20)
        k = self.kpis()['stock_critico']
        self.assertEqual((k.texto, k.cumple), ('10 %', True))

    def test_tiempo_promedio_de_reparacion(self):
        ahora = timezone.now()
        e = self.crear_equipo(valor=Decimal('1000'))
        for dias_diagnostico, dias_resolucion, decision in [(5, 2, 'completado'), (10, 1, 'completado'),
                                                            (3, 1, 'dar_baja'), (400, 390, 'completado')]:
            m = Mantenimiento.objects.create(equipo=e, decision=decision)
            Mantenimiento.objects.filter(id=m.id).update(
                fecha_diagnostico=ahora - timedelta(days=dias_diagnostico),
                fecha_resolucion=ahora - timedelta(days=dias_resolucion),
            )
        k = self.kpis()['reparacion_dias']
        self.assertAlmostEqual(k.valor, 6)
        self.assertEqual((k.texto, k.cumple), ('6 días', True))


class ReportesKpiVistaTests(LeicaTestCase):

    def test_reportes_muestra_los_kpi(self):
        self.crear_equipo()
        self.client.force_login(self.director)
        r = self.client.get('/reportes/')
        self.assertEqual(r.context['periodo'], 30)
        self.assertEqual(len(r.context['kpis']), 7)
        self.assertContains(r, 'Indicadores clave (KPI)')
        self.assertContains(r, 'data-kpi="disponibilidad"')

    def test_periodo_valido_e_invalido(self):
        self.client.force_login(self.director)
        self.assertEqual(self.client.get('/reportes/', {'periodo': '90'}).context['periodo'], 90)
        for valor in ('15', 'abc', '-7'):
            with self.subTest(valor=valor):
                self.assertEqual(self.client.get('/reportes/', {'periodo': valor}).context['periodo'], 30)

    def test_estudiante_no_ve_los_kpi(self):
        self.client.force_login(self.estudiante)
        self.assertEqual(self.client.get('/reportes/').status_code, 302)


class KpiFormatoTests(LeicaTestCase):

    def test_aprobacion_de_menos_de_una_hora_en_minutos_y_singular(self):
        ahora = timezone.now()
        s = self.crear_solicitud(self.estudiante, estado=Solicitud.EstadoSolicitud.APROBADA)
        Solicitud.objects.filter(id=s.id).update(created_at=ahora - timedelta(minutes=45), fecha_aprobacion=ahora)
        k = {k.clave: k for k in calcular_kpis(30)}['aprobacion_horas']
        self.assertEqual((k.texto, k.cumple), ('45 min', True))
        self.assertEqual(k.detalle, '1 solicitud aprobada')
