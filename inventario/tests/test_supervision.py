from datetime import timedelta
from io import BytesIO

from django.core import mail
from django.test import override_settings
from django.utils import timezone
from openpyxl import load_workbook

from inventario import tareas
from inventario.kpi import brechas_busqueda, calcular_calidad_ia, calcular_sla
from inventario.models import BusquedaIA, Equipo, Solicitud

from .base import LeicaTestCase


def por_clave(indicadores):
    return {k.clave: k for k in indicadores}


class RevisionTests(LeicaTestCase):

    def setUp(self):
        self.client.force_login(self.encargado)

    def test_aprobar_y_rechazar_registran_la_revision(self):
        aprobada = self.crear_solicitud(self.estudiante, equipos=[self.crear_equipo()])
        rechazada = self.crear_solicitud(self.estudiante, equipos=[self.crear_equipo('LTV-002')])
        self.accion_solicitud(aprobada, 'aprobar')
        self.accion_solicitud(rechazada, 'rechazar', motivo_rechazo='Sin cupo')
        aprobada.refresh_from_db()
        rechazada.refresh_from_db()
        self.assertEqual(aprobada.revisada_en, aprobada.fecha_aprobacion)
        self.assertIsNotNone(rechazada.revisada_en)

    def test_rechazar_despues_de_aprobar_conserva_la_primera_revision(self):
        s = self.crear_solicitud(self.estudiante, equipos=[self.crear_equipo()])
        self.accion_solicitud(s, 'aprobar')
        s.refresh_from_db()
        primera = s.revisada_en
        self.accion_solicitud(s, 'rechazar', motivo_rechazo='Equipo dañado')
        s.refresh_from_db()
        self.assertEqual(s.revisada_en, primera)


@override_settings(SLA_REVISION_HORAS=24, SLA_BAJA_DIAS=5)
class SlaTests(LeicaTestCase):

    def solicitud(self, horas_creada, horas_revision=None, estado=Solicitud.EstadoSolicitud.APROBADA):
        s = self.crear_solicitud(self.estudiante, estado=estado)
        creada = timezone.now() - timedelta(hours=horas_creada)
        revisada = creada + timedelta(hours=horas_revision) if horas_revision is not None else None
        Solicitud.objects.filter(id=s.id).update(created_at=creada, revisada_en=revisada)
        return s

    def test_sin_datos(self):
        sla = por_clave(calcular_sla())
        self.assertIsNone(sla['revision_a_tiempo'].valor)
        self.assertIsNone(sla['aprobacion_directa'].valor)
        self.assertTrue(sla['pendientes_vencidas'].cumple)

    def test_revision_a_tiempo_y_aprobacion_directa(self):
        self.solicitud(48, 2)
        self.solicitud(48, 30)
        self.solicitud(10, 1, estado=Solicitud.EstadoSolicitud.RECHAZADA)
        self.solicitud(10, 5, estado=Solicitud.EstadoSolicitud.DEVUELTA)
        sla = por_clave(calcular_sla())
        self.assertEqual(sla['revision_a_tiempo'].valor, 75)
        self.assertFalse(sla['revision_a_tiempo'].cumple)
        self.assertEqual(sla['aprobacion_directa'].valor, 75)
        self.assertEqual(sla['aprobacion_directa'].detalle, '3 de 4 solicitudes revisadas')

    def test_revisiones_fuera_del_periodo_no_cuentan(self):
        self.solicitud(24 * 40, 1)
        self.assertIsNone(por_clave(calcular_sla(30))['revision_a_tiempo'].valor)

    def test_pendientes_fuera_de_plazo(self):
        self.solicitud(30, estado=Solicitud.EstadoSolicitud.PENDIENTE)
        self.solicitud(2, estado=Solicitud.EstadoSolicitud.PENDIENTE)
        indicador = por_clave(calcular_sla())['pendientes_vencidas']
        self.assertEqual((indicador.valor, indicador.cumple), (1, False))

    def test_bajas_sin_validar(self):
        vieja = self.crear_equipo('B-1', estado=Equipo.Estado.PENDIENTE_BAJA)
        self.crear_equipo('B-2', estado=Equipo.Estado.PENDIENTE_BAJA)
        Equipo.objects.filter(id=vieja.id).update(updated_at=timezone.now() - timedelta(days=6))
        self.assertEqual(por_clave(calcular_sla())['bajas_sin_validar'].valor, 1)


class CalidadIaTests(LeicaTestCase):

    def busqueda(self, usuario=None, **campos):
        campos.setdefault('consulta', 'osciloscopio')
        campos.setdefault('resultados', 3)
        return BusquedaIA.objects.create(usuario=usuario or self.estudiante, fuente='hibrida_local', **campos)

    def test_sin_datos(self):
        calidad = por_clave(calcular_calidad_ia())
        self.assertIsNone(calidad['fidelidad_citas'].valor)
        self.assertIsNone(calidad['respuestas_utiles'].valor)
        self.assertIsNone(calidad['escalado'].valor)

    def test_fidelidad_utilidad_y_escalado(self):
        for _ in range(3):
            self.busqueda(generacion=BusquedaIA.Generacion.GENERADA, util=True)
        self.busqueda(generacion=BusquedaIA.Generacion.DESCARTADA, util=False)
        self.busqueda(resultados=0)
        calidad = por_clave(calcular_calidad_ia())
        self.assertEqual(calidad['fidelidad_citas'].valor, 75)
        self.assertEqual(calidad['respuestas_utiles'].valor, 75)
        self.assertEqual(calidad['escalado'].valor, 40)
        self.assertFalse(calidad['escalado'].cumple)

    def test_adopcion_cuenta_usuarios_con_busquedas_o_solicitudes(self):
        self.busqueda()
        self.busqueda()
        self.crear_solicitud(self.docente)
        adopcion = por_clave(calcular_calidad_ia())['adopcion']
        self.assertEqual(adopcion.detalle, '2 de 6 usuarios activos')
        self.assertAlmostEqual(adopcion.valor, 33.33, places=2)

    def test_brechas_agrupan_consultas_sin_resultado_o_no_utiles(self):
        self.busqueda(resultados=0, consulta=' Cafetera ')
        self.busqueda(resultados=0, consulta='cafetera')
        self.busqueda(util=False, consulta='router para wifi')
        self.busqueda(util=True, consulta='osciloscopio')
        brechas = brechas_busqueda()
        self.assertEqual([(b['texto'], b['veces'], b['sin_resultados'], b['no_utiles']) for b in brechas],
                         [('cafetera', 2, 2, 0), ('router para wifi', 1, 0, 1)])


@override_settings(SLA_REVISION_HORAS=24)
class EscalamientoTests(LeicaTestCase):

    def pendiente(self, horas):
        s = self.crear_solicitud(self.estudiante, equipos=[self.crear_equipo(f'E-{horas}')])
        Solicitud.objects.filter(id=s.id).update(created_at=timezone.now() - timedelta(hours=horas))
        return s

    def test_avisa_una_vez_a_quienes_aprueban(self):
        vencida = self.pendiente(30)
        self.pendiente(2)
        self.assertEqual(tareas.ejecutar()['revisiones_escaladas'], 1)
        correo, = mail.outbox
        self.assertEqual(sorted(correo.to), sorted(u.email for u in (self.encargado, self.calidad, self.director)))
        self.assertIn('más de 24 h (1)', correo.subject)
        self.assertIn(f'#{vencida.id}', correo.body)
        self.assertEqual(tareas.ejecutar()['revisiones_escaladas'], 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_sin_vencidas_no_envia(self):
        self.pendiente(2)
        self.assertEqual(tareas.ejecutar()['revisiones_escaladas'], 0)
        self.assertEqual(mail.outbox, [])

    def test_si_el_correo_falla_reintenta_despues(self):
        self.pendiente(30)
        with self.settings(EMAIL_BACKEND='inventario.tests.test_supervision.CorreoCaido'):
            self.assertEqual(tareas.ejecutar()['revisiones_escaladas'], 0)
        self.assertEqual(tareas.ejecutar()['revisiones_escaladas'], 1)

    def test_sin_aprobadores_con_correo_marca_igual(self):
        from inventario.models import Usuario
        Usuario.objects.filter(rol__in=Usuario.ROLES_APROBADORES).update(is_active=False)
        self.pendiente(30)
        self.assertEqual(tareas.ejecutar()['revisiones_escaladas'], 1)


class CorreoCaido:

    def __init__(self, *args, **kwargs):
        pass

    def send_messages(self, mensajes):
        raise OSError('smtp caído')


class ReportesSupervisionTests(LeicaTestCase):

    def test_reportes_muestran_sla_calidad_ia_y_brechas(self):
        BusquedaIA.objects.create(usuario=self.estudiante, consulta='cafetera', fuente='hibrida_local', resultados=0)
        self.client.force_login(self.comite)
        r = self.client.get('/reportes/')
        for ancla in ('id="supervision"', 'id="calidad-ia"', 'id="brechas"', 'data-kpi="adopcion"',
                      'data-kpi="revision_a_tiempo"', 'cafetera'):
            self.assertContains(r, ancla)

    def test_excel_incluye_brechas_e_indicadores_nuevos(self):
        BusquedaIA.objects.create(usuario=self.estudiante, consulta='cafetera', fuente='hibrida_local', resultados=0)
        self.client.force_login(self.comite)
        libro = load_workbook(BytesIO(self.client.get('/reportes/exportar/').content))
        self.assertEqual(libro['Brechas búsqueda']['A5'].value, 'cafetera')
        tipos = {c.value for c in libro['Indicadores']['B']}
        self.assertTrue({'SLA', 'Calidad IA'} <= tipos)
