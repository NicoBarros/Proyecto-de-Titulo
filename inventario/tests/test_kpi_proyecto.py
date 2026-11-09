"""
KPI de la sección 12 del documento: registro de búsquedas (Busqueda_IA), conflictos de reserva y bloqueos.
"""
from datetime import timedelta

from django.utils import timezone

from inventario.kpi import calcular_kpis_proyecto
from inventario.models import Bloqueo, BusquedaIA, ConflictoReserva, Equipo, Solicitud

from .base import LeicaTestCase


class RegistroBusquedasTests(LeicaTestCase):

    def setUp(self):
        self.client.force_login(self.estudiante)
        self.osc = self.crear_equipo('K-1', 'Osciloscopio')

    def buscar(self, consulta):
        return self.client.post('/busqueda/', {'consulta': consulta}).json()

    def test_cada_busqueda_queda_registrada(self):
        data = self.buscar('osciloscopio')
        b = BusquedaIA.objects.get()
        self.assertEqual(data['busqueda'], b.id)
        self.assertEqual((b.usuario, b.consulta, b.fuente, b.resultados, b.reformulacion),
                         (self.estudiante, 'osciloscopio', 'palabras_clave_local', 1, False))
        self.assertTrue(data['resultados'][0]['url'].endswith(f'?busqueda={b.id}'))

    def test_abrir_un_resultado_registra_la_eleccion(self):
        data = self.buscar('osciloscopio')
        self.client.get(data['resultados'][0]['url'])
        b = BusquedaIA.objects.get()
        self.assertEqual(b.equipo_elegido, self.osc)
        self.assertIsNotNone(b.elegida_en)

    def test_la_eleccion_solo_se_registra_una_vez_y_por_su_autor(self):
        b_id = self.buscar('osciloscopio')['busqueda']
        otro = self.crear_equipo('K-2', 'Multimetro')
        self.client.force_login(self.docente)
        self.client.get(f'/inventario/equipo/{otro.id}/?busqueda={b_id}')
        self.assertIsNone(BusquedaIA.objects.get().equipo_elegido)
        self.client.force_login(self.estudiante)
        self.client.get(f'/inventario/equipo/{self.osc.id}/?busqueda={b_id}')
        self.client.get(f'/inventario/equipo/{otro.id}/?busqueda={b_id}')
        self.assertEqual(BusquedaIA.objects.get().equipo_elegido, self.osc)
        self.assertEqual(self.client.get(f'/inventario/equipo/{otro.id}/?busqueda=abc').status_code, 200)

    def test_volver_a_buscar_sin_elegir_es_reformulacion(self):
        self.buscar('algo para medir')
        self.buscar('osciloscopio')
        self.assertEqual(list(BusquedaIA.objects.order_by('id').values_list('reformulacion', flat=True)), [False, True])

    def test_buscar_despues_de_elegir_no_es_reformulacion(self):
        data = self.buscar('osciloscopio')
        self.client.get(data['resultados'][0]['url'])
        self.buscar('multimetro')
        self.assertFalse(BusquedaIA.objects.latest('id').reformulacion)


class RegistroConflictosTests(LeicaTestCase):

    def test_solicitar_equipo_no_disponible_registra_conflicto(self):
        equipo = self.crear_equipo('C-1', estado=Equipo.Estado.EN_MANTENIMIENTO)
        self.client.force_login(self.docente)
        inicio = timezone.now() + timedelta(hours=1)
        self.client.post('/solicitudes/', {
            'item[]': [f'equipo:{equipo.id}'], 'cantidad[]': ['1'],
            'horario_inicio': inicio.isoformat(), 'horario_fin': (inicio + timedelta(hours=2)).isoformat(),
        })
        conflicto = ConflictoReserva.objects.get()
        self.assertEqual((conflicto.usuario, conflicto.equipo, conflicto.solicitud), (self.docente, equipo, None))
        self.assertFalse(Solicitud.objects.exists())

    def test_aprobar_con_horario_ocupado_registra_conflicto(self):
        equipo = self.crear_equipo('C-1')
        self.crear_solicitud(self.docente, equipos=[equipo], estado=Solicitud.EstadoSolicitud.APROBADA)
        pendiente = self.crear_solicitud(self.estudiante, equipos=[equipo])
        self.client.force_login(self.encargado)
        self.accion_solicitud(pendiente, 'aprobar')
        conflicto = ConflictoReserva.objects.get()
        self.assertEqual((conflicto.equipo, conflicto.solicitud), (equipo, pendiente))
        self.assertIn('reservado en ese horario', conflicto.motivo)
        pendiente.refresh_from_db()
        self.assertEqual(pendiente.estado, Solicitud.EstadoSolicitud.PENDIENTE)

    def test_otros_errores_no_son_conflictos(self):
        self.client.force_login(self.docente)
        self.client.post('/solicitudes/', {'item[]': ['equipo:999999'], 'cantidad[]': ['1']})
        self.assertFalse(ConflictoReserva.objects.exists())


class KpiProyectoTests(LeicaTestCase):

    def kpis(self, dias=30):
        return {k.clave: k for k in calcular_kpis_proyecto(dias)}

    def busqueda(self, duracion_ms, reformulacion=False, elegida_tras=None, hace_dias=0):
        equipo = self.crear_equipo(f'B-{BusquedaIA.objects.count()}') if elegida_tras is not None else None
        b = BusquedaIA.objects.create(usuario=self.estudiante, consulta='x', fuente='semantica_local',
                                      duracion_ms=duracion_ms, reformulacion=reformulacion, equipo_elegido=equipo)
        fecha = timezone.now() - timedelta(days=hace_dias)
        BusquedaIA.objects.filter(id=b.id).update(
            fecha=fecha, elegida_en=fecha + timedelta(seconds=elegida_tras) if elegida_tras is not None else None,
        )

    def test_sin_datos(self):
        k = self.kpis()
        for clave in ('devoluciones_a_tiempo', 'busqueda_segundos', 'busquedas_primer_intento'):
            self.assertIsNone(k[clave].valor)
        self.assertEqual((k['conflictos_evitados'].valor, k['conflictos_evitados'].seguimiento), (0, True))
        self.assertEqual((k['bloqueos_atraso'].valor, k['bloqueos_atraso'].cumple), (0, True))

    def test_tiempo_de_busqueda_y_primer_intento(self):
        self.busqueda(200, elegida_tras=10)
        self.busqueda(400)
        self.busqueda(600, reformulacion=True, elegida_tras=20)
        self.busqueda(9000, hace_dias=40)
        k = self.kpis()
        self.assertAlmostEqual(k['busqueda_segundos'].valor, 0.4)
        self.assertEqual(k['busqueda_segundos'].texto, '400 ms')
        self.assertTrue(k['busqueda_segundos'].cumple)
        self.assertEqual(k['busqueda_segundos'].detalle, '3 búsquedas · 15 s hasta elegir un equipo')
        self.assertEqual(k['busquedas_primer_intento'].valor, 50)
        self.assertFalse(k['busquedas_primer_intento'].cumple)
        self.assertEqual(k['busquedas_primer_intento'].detalle, '1 de 2 primeras consultas')

    def test_busqueda_lenta_no_cumple(self):
        self.busqueda(4500)
        k = self.kpis()['busqueda_segundos']
        self.assertEqual((k.texto, k.cumple), ('4,5 s', False))

    def test_conflictos_evitados_del_periodo(self):
        equipo = self.crear_equipo()
        ConflictoReserva.objects.create(equipo=equipo, motivo='a')
        ConflictoReserva.objects.create(equipo=equipo, motivo='b')
        viejo = ConflictoReserva.objects.create(equipo=equipo, motivo='c')
        ConflictoReserva.objects.filter(id=viejo.id).update(fecha=timezone.now() - timedelta(days=60))
        k = self.kpis()['conflictos_evitados']
        self.assertEqual((k.valor, k.detalle, k.cumple), (2, '1 equipo involucrado', None))

    def test_bloqueos_se_comparan_con_el_periodo_anterior(self):
        def bloqueo(hace_dias):
            b = Bloqueo.objects.create(usuario=self.estudiante, fecha_fin=timezone.now() + timedelta(days=7))
            Bloqueo.objects.filter(id=b.id).update(fecha_inicio=timezone.now() - timedelta(days=hace_dias))
        bloqueo(5)
        bloqueo(40)
        bloqueo(45)
        k = self.kpis()['bloqueos_atraso']
        self.assertEqual((k.valor, k.meta, k.cumple, k.objetivo), (1, 2, True, '≤ 2 (período anterior)'))
        bloqueo(6)
        bloqueo(7)
        self.assertFalse(self.kpis()['bloqueos_atraso'].cumple)
