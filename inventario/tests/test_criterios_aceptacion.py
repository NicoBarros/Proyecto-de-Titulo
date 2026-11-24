from datetime import timedelta
from io import BytesIO

from django.contrib.messages import get_messages
from django.core import mail
from django.utils import timezone
from openpyxl import load_workbook

from inventario.models import Bloqueo, Solicitud, Usuario
from inventario.rag import MAX_RESULTADOS

from .base import LeicaTestCase


def mensajes(respuesta):
    return [str(m) for m in get_messages(respuesta.wsgi_request)]


class ConflictoEdicionTests(LeicaTestCase):

    def setUp(self):
        self.client.force_login(self.encargado)

    def test_equipo_con_version_vigente_se_guarda(self):
        e = self.crear_equipo()
        r = self.client.post(f'/inventario/equipo/{e.id}/editar/', {
            'codigo_inventario': e.codigo_inventario, 'nombre': 'Nuevo', 'version': '1',
        })
        self.assertEqual(r.status_code, 302)
        e.refresh_from_db()
        self.assertEqual((e.nombre, e.version), ('Nuevo', 2))

    def test_equipo_modificado_por_otro_advierte_y_no_sobrescribe(self):
        e = self.crear_equipo()
        e.nombre = 'Cambio de calidad'
        e.version = 2
        e.save()
        r = self.client.post(f'/inventario/equipo/{e.id}/editar/', {
            'codigo_inventario': e.codigo_inventario, 'nombre': 'Cambio del encargado', 'version': '1',
        })
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context['conflicto'])
        self.assertContains(r, 'conflicto-edicion')
        self.assertContains(r, 'name="version" value="2"')
        e.refresh_from_db()
        self.assertEqual((e.nombre, e.version), ('Cambio de calidad', 2))

    def test_guardar_tras_el_aviso_sobrescribe(self):
        e = self.crear_equipo(version=2)
        r = self.client.post(f'/inventario/equipo/{e.id}/editar/', {
            'codigo_inventario': e.codigo_inventario, 'nombre': 'Confirmado', 'version': '2',
        })
        self.assertEqual(r.status_code, 302)
        e.refresh_from_db()
        self.assertEqual((e.nombre, e.version), ('Confirmado', 3))

    def test_formulario_incluye_version(self):
        e = self.crear_equipo()
        self.assertContains(self.client.get(f'/inventario/equipo/{e.id}/editar/'), 'name="version" value="1"')

    def test_insumo_modificado_por_otro_advierte(self):
        i = self.crear_insumo()
        i.version = 3
        i.save()
        r = self.client.post(f'/inventario/insumo/{i.id}/editar/', {
            'nombre': 'Otro', 'tipo': 'renovable', 'cantidad_total': '10', 'umbral_minimo': '2', 'version': '1',
        })
        self.assertTrue(r.context['conflicto'])
        i.refresh_from_db()
        self.assertEqual((i.nombre, i.version), ('Protoboard', 3))


class MotivoRechazoTests(LeicaTestCase):

    def setUp(self):
        self.client.force_login(self.encargado)
        self.solicitud = self.crear_solicitud(self.estudiante, equipos=[self.crear_equipo()])

    def test_rechazo_sin_motivo_no_procede(self):
        r = self.accion_solicitud(self.solicitud, 'rechazar', motivo_rechazo='   ')
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, Solicitud.EstadoSolicitud.PENDIENTE)
        self.assertIn('Indica el motivo del rechazo.', mensajes(r))

    def test_rechazo_guarda_el_motivo_y_lo_notifica(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.accion_solicitud(self.solicitud, 'rechazar', motivo_rechazo='Equipo reservado para examen')
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, Solicitud.EstadoSolicitud.RECHAZADA)
        self.assertEqual(self.solicitud.motivo_rechazo, 'Equipo reservado para examen')
        self.assertIn('Motivo: Equipo reservado para examen', mail.outbox[0].body)

    def test_el_solicitante_ve_el_motivo(self):
        self.accion_solicitud(self.solicitud, 'rechazar', motivo_rechazo='Sin stock')
        self.client.force_login(self.estudiante)
        self.assertContains(self.client.get('/solicitudes/'), 'Sin stock')

    def test_listado_ofrece_modal_de_rechazo(self):
        html = self.client.get('/solicitudes/').content.decode()
        self.assertIn(f'id="rechazo-{self.solicitud.id}"', html)
        self.assertIn('name="motivo_rechazo"', html)


class BloqueoSeccionTests(LeicaTestCase):

    def setUp(self):
        self.companero = self.crear_usuario('companero', Usuario.Rol.ESTUDIANTE, seccion='TIN-401')
        self.otra_seccion = self.crear_usuario('otro', Usuario.Rol.ESTUDIANTE, seccion='TIN-402')
        self.inicio = timezone.now() + timedelta(days=1)

    def solicitar(self, usuario, **extra):
        self.client.force_login(usuario)
        equipo = self.crear_equipo(codigo=f'LTV-{Solicitud.objects.count() + 100}')
        return self.client.post('/solicitudes/', {
            'item[]': [f'equipo:{equipo.id}'], 'cantidad[]': ['1'], 'lugar_uso': 'dentro_sede',
            'horario_inicio': self.inicio.strftime('%Y-%m-%dT%H:%M'),
            'horario_fin': (self.inicio + timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M'), **extra,
        })

    def devolver_con_atraso(self):
        equipo = self.crear_equipo(codigo='LTV-900')
        s = self.crear_solicitud(
            self.estudiante, equipos=[equipo], estado=Solicitud.EstadoSolicitud.ATRASADA,
            inicio=timezone.now() - timedelta(days=2), fin=timezone.now() - timedelta(days=1),
        )
        self.client.force_login(self.encargado)
        self.accion_solicitud(s, 'devolver')
        return s

    def test_atraso_bloquea_a_la_seccion(self):
        self.devolver_con_atraso()
        self.assertEqual(Bloqueo.objects.get().seccion, 'TIN-401')
        r = self.solicitar(self.companero)
        self.assertFalse(Solicitud.objects.filter(solicitante=self.companero).exists())
        self.assertTrue(any('La sección TIN-401 está bloqueada' in m for m in mensajes(r)))

    def test_otra_seccion_no_se_ve_afectada(self):
        self.devolver_con_atraso()
        self.solicitar(self.otra_seccion)
        self.assertTrue(Solicitud.objects.filter(solicitante=self.otra_seccion).exists())

    def test_docente_no_puede_representar_a_estudiante_de_seccion_bloqueada(self):
        self.devolver_con_atraso()
        r = self.solicitar(self.docente, en_representacion_de=str(self.companero.id))
        self.assertFalse(Solicitud.objects.filter(solicitante=self.docente).exists())
        self.assertTrue(any('TIN-401' in m for m in mensajes(r)))

    def test_bloqueo_vencido_libera_la_seccion(self):
        self.devolver_con_atraso()
        Bloqueo.objects.update(fecha_fin=timezone.now() - timedelta(minutes=1))
        self.solicitar(self.companero)
        self.assertTrue(Solicitud.objects.filter(solicitante=self.companero).exists())

    def test_sancion_a_no_estudiante_no_bloquea_seccion(self):
        self.docente.seccion = 'TIN-401'
        self.docente.save()
        equipo = self.crear_equipo(codigo='LTV-901')
        s = self.crear_solicitud(
            self.docente, equipos=[equipo], estado=Solicitud.EstadoSolicitud.ATRASADA,
            inicio=timezone.now() - timedelta(days=2), fin=timezone.now() - timedelta(days=1),
        )
        self.client.force_login(self.encargado)
        self.accion_solicitud(s, 'devolver')
        self.assertIsNone(Bloqueo.objects.get().seccion)

    def test_desbloqueo_manual_libera_la_seccion(self):
        self.devolver_con_atraso()
        self.client.force_login(self.encargado)
        self.client.post('/panel-admin/', {'accion': 'desbloquear', 'user_id': self.estudiante.id})
        self.solicitar(self.companero)
        self.assertTrue(Solicitud.objects.filter(solicitante=self.companero).exists())

    def test_modal_de_devolucion_advierte_la_seccion(self):
        equipo = self.crear_equipo(codigo='LTV-902')
        self.crear_solicitud(
            self.estudiante, equipos=[equipo], estado=Solicitud.EstadoSolicitud.ATRASADA,
            inicio=timezone.now() - timedelta(days=2), fin=timezone.now() - timedelta(days=1),
        )
        self.client.force_login(self.encargado)
        self.assertContains(self.client.get('/solicitudes/'), 'y a la sección TIN-401')


class ResultadosBusquedaTests(LeicaTestCase):

    def test_maximo_cinco_resultados(self):
        self.assertEqual(MAX_RESULTADOS, 5)


class ExportarReportesTests(LeicaTestCase):

    def test_exporta_excel_con_todas_las_hojas(self):
        equipo = self.crear_equipo(modelo='Fluke 117')
        self.crear_solicitud(
            self.estudiante, equipos=[equipo], estado=Solicitud.EstadoSolicitud.ATRASADA,
            inicio=timezone.now() - timedelta(days=3), fin=timezone.now() - timedelta(days=2),
        )
        self.crear_equipo(codigo='LTV-002', nombre='Osciloscopio')
        self.client.force_login(self.comite)
        r = self.client.get('/reportes/exportar/', {'periodo': '30', 'dias': '30'})
        self.assertEqual(r.status_code, 200)
        self.assertIn('reportes_leica_', r['Content-Disposition'])
        libro = load_workbook(BytesIO(r.content))
        self.assertEqual(libro.sheetnames, [
            'Indicadores', 'Más solicitados', 'Préstamos vencidos', 'Sin movimiento', 'Brechas búsqueda',
        ])
        self.assertIn('30 días', libro['Indicadores']['A1'].value)
        self.assertEqual(libro['Más solicitados']['A5'].value, 'Multimetro')
        vencidos = libro['Préstamos vencidos']
        self.assertEqual(vencidos['C5'].value, 'TIN-401')
        self.assertEqual(vencidos['G5'].value, 2)
        self.assertEqual(libro['Sin movimiento']['A5'].value, 'Osciloscopio')
        self.assertGreater(libro['Indicadores'].max_row, 5)

    def test_estudiante_no_puede_exportar(self):
        self.client.force_login(self.estudiante)
        self.assertEqual(self.client.get('/reportes/exportar/').status_code, 302)

    def test_reportes_muestra_boton_de_exportar(self):
        self.client.force_login(self.comite)
        self.assertContains(self.client.get('/reportes/', {'periodo': '7', 'dias': '15'}),
                            '/reportes/exportar/?periodo=7&dias=15')
