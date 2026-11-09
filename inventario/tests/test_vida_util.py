"""
RF-14 / HU-14: los equipos con más de 4 años de antigüedad quedan pendientes de baja.
"""
from datetime import date, datetime, timedelta
from io import BytesIO

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from openpyxl import Workbook

from inventario import servicios, tareas
from inventario.models import Equipo, HistorialEquipo, Mantenimiento, Usuario

from .base import LeicaTestCase


def hace_años(años, dias=0):
    hoy = timezone.localdate()
    return hoy.replace(year=hoy.year - años) - timedelta(days=dias)


class VidaUtilTests(LeicaTestCase):

    def antiguo(self, codigo='VU-1', **extra):
        return self.crear_equipo(codigo, 'Osciloscopio antiguo', fecha_adquisicion=hace_años(4, dias=1), **extra)

    def recargar(self, equipo):
        equipo.refresh_from_db()
        return equipo.estado

    def test_supera_vida_util_solo_con_mas_de_cuatro_años(self):
        self.assertTrue(Equipo(fecha_adquisicion=hace_años(4, dias=1)).supera_vida_util())
        self.assertFalse(Equipo(fecha_adquisicion=hace_años(4)).supera_vida_util())
        self.assertFalse(Equipo(fecha_adquisicion=None).supera_vida_util())

    def test_verificacion_periodica_marca_pendientes_de_baja(self):
        viejo = self.antiguo()
        nuevo = self.crear_equipo('VU-2', fecha_adquisicion=hace_años(1))
        sin_fecha = self.crear_equipo('VU-3')
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(tareas.ejecutar()['pendientes_baja_marcados'], 1)
        self.assertEqual(self.recargar(viejo), Equipo.Estado.PENDIENTE_BAJA)
        self.assertEqual(self.recargar(nuevo), Equipo.Estado.DISPONIBLE)
        self.assertEqual(self.recargar(sin_fecha), Equipo.Estado.DISPONIBLE)
        registro = viejo.historial.get(accion=HistorialEquipo.Accion.ESTADO)
        self.assertEqual(registro.cambios['estado'], ['disponible', 'pendiente_baja'])
        self.assertEqual(tareas.ejecutar()['pendientes_baja_marcados'], 0)

    def test_notifica_a_control_de_calidad_en_un_solo_correo(self):
        self.antiguo('VU-1')
        self.antiguo('VU-2')
        with self.captureOnCommitCallbacks(execute=True):
            servicios.marcar_pendientes_baja()
        self.assertEqual(len(mail.outbox), 1)
        correo = mail.outbox[0]
        self.assertEqual(correo.to, ['calidad@inacapmail.cl'])
        self.assertEqual(correo.subject, 'Equipos pendientes de baja (2)')
        self.assertIn('VU-1', correo.body)
        self.assertIn('VU-2', correo.body)
        self.assertIn('?estado=pendiente_baja', correo.body)

    def test_sin_control_de_calidad_activo_no_envia_correo(self):
        Usuario.objects.filter(rol=Usuario.Rol.CONTROL_CALIDAD).update(is_active=False)
        self.antiguo()
        with self.captureOnCommitCallbacks(execute=True):
            servicios.marcar_pendientes_baja()
        self.assertEqual(mail.outbox, [])

    def test_no_cambia_equipos_prestados_ni_dados_de_baja(self):
        prestado = self.antiguo('VU-1', estado=Equipo.Estado.PRESTADO)
        baja = self.antiguo('VU-2', estado=Equipo.Estado.FUERA_SERVICIO)
        servicios.marcar_pendientes_baja()
        self.assertEqual(self.recargar(prestado), Equipo.Estado.PRESTADO)
        self.assertEqual(self.recargar(baja), Equipo.Estado.FUERA_SERVICIO)

    def test_al_volver_a_disponible_queda_pendiente_de_baja(self):
        equipo = self.antiguo(estado=Equipo.Estado.EN_MANTENIMIENTO)
        mant = Mantenimiento.objects.create(equipo=equipo, falla_descrita='Pantalla', costo_cotizado=1000)
        with self.captureOnCommitCallbacks(execute=True):
            servicios.resolver_mantenimiento(self.calidad, mant.id, 'completar_reparacion')
        self.assertEqual(self.recargar(equipo), Equipo.Estado.PENDIENTE_BAJA)
        self.assertIn('Supera 4 años', equipo.historial.latest('fecha').detalle)
        self.assertEqual(len(mail.outbox), 1)

    def test_devolucion_de_equipo_antiguo_queda_pendiente_de_baja(self):
        self.client.force_login(self.encargado)
        equipo = self.crear_equipo('VU-1', fecha_adquisicion=hace_años(5))
        solicitud = self.crear_solicitud(self.estudiante, equipos=[equipo])
        equipo.estado = Equipo.Estado.PRESTADO
        equipo.save()
        solicitud.estado = solicitud.EstadoSolicitud.ENTREGADA
        solicitud.save()
        self.accion_solicitud(solicitud, 'devolver', estado_equipo='bueno')
        self.assertEqual(self.recargar(equipo), Equipo.Estado.PENDIENTE_BAJA)

    def test_cambio_manual_a_disponible_se_rechaza(self):
        equipo = self.antiguo(estado=Equipo.Estado.PENDIENTE_BAJA)
        with self.assertRaisesMessage(ValueError, 'supera 4 años'):
            servicios.cambiar_estado_manual(equipo, self.calidad, Equipo.Estado.DISPONIBLE, 'Panel')
        servicios.cambiar_estado_manual(equipo, self.calidad, Equipo.Estado.FUERA_SERVICIO, 'Panel')
        self.assertEqual(self.recargar(equipo), Equipo.Estado.FUERA_SERVICIO)

    def test_pendiente_de_baja_no_se_puede_solicitar(self):
        equipo = self.antiguo(estado=Equipo.Estado.PENDIENTE_BAJA)
        inicio = timezone.now() + timedelta(hours=1)
        with self.assertRaisesMessage(ValueError, 'no se encuentra disponible'):
            servicios.crear_solicitud(self.docente, [f'equipo:{equipo.id}'], [], inicio, inicio + timedelta(hours=2), None, 'Clase')

    def test_pendiente_de_baja_no_aparece_en_la_busqueda(self):
        self.antiguo(estado=Equipo.Estado.PENDIENTE_BAJA)
        self.client.force_login(self.estudiante)
        self.assertEqual(self.client.post('/busqueda/', {'consulta': 'osciloscopio'}).json()['resultados'], [])


class RegistroConFechaTests(LeicaTestCase):

    def setUp(self):
        self.client.force_login(self.encargado)

    def crear(self, fecha):
        return self.client.post('/inventario/?tab=equipos', {
            'codigo_inventario': 'RF-1', 'nombre': 'Router', 'fecha_adquisicion': fecha,
        }, follow=True)

    def test_registrar_equipo_antiguo_queda_pendiente_de_baja(self):
        with self.captureOnCommitCallbacks(execute=True):
            r = self.crear(hace_años(6).isoformat())
        equipo = Equipo.objects.get(codigo_inventario='RF-1')
        self.assertEqual(equipo.estado, Equipo.Estado.PENDIENTE_BAJA)
        self.assertContains(r, 'quedó pendiente de baja')
        self.assertEqual(len(mail.outbox), 1)

    def test_registrar_equipo_reciente_queda_disponible(self):
        self.crear(hace_años(1).isoformat())
        self.assertEqual(Equipo.objects.get(codigo_inventario='RF-1').estado, Equipo.Estado.DISPONIBLE)

    def test_fecha_futura_se_rechaza(self):
        self.crear((timezone.localdate() + timedelta(days=1)).isoformat())
        self.assertFalse(Equipo.objects.filter(codigo_inventario='RF-1').exists())

    def test_editar_fecha_marca_y_corregirla_libera(self):
        equipo = self.crear_equipo('RF-2', 'Switch')
        datos = {'codigo_inventario': 'RF-2', 'nombre': 'Switch'}
        self.client.post(f'/inventario/equipo/{equipo.id}/editar/', {**datos, 'fecha_adquisicion': hace_años(5).isoformat()})
        equipo.refresh_from_db()
        self.assertEqual(equipo.estado, Equipo.Estado.PENDIENTE_BAJA)
        self.client.post(f'/inventario/equipo/{equipo.id}/editar/', {**datos, 'fecha_adquisicion': hace_años(2).isoformat()})
        equipo.refresh_from_db()
        self.assertEqual(equipo.estado, Equipo.Estado.DISPONIBLE)
        historial = HistorialEquipo.objects.filter(equipo=equipo, accion=HistorialEquipo.Accion.ESTADO)
        self.assertEqual([h.detalle for h in historial.order_by('id')], ['Supera 4 años de antigüedad', 'Fecha de adquisición corregida'])

    def test_ficha_e_historial_muestran_la_fecha(self):
        equipo = self.crear_equipo('RF-3', fecha_adquisicion=date(2021, 3, 15))
        self.assertContains(self.client.get(f'/inventario/equipo/{equipo.id}/'), '15/03/2021')
        self.client.post(f'/inventario/equipo/{equipo.id}/editar/', {
            'codigo_inventario': 'RF-3', 'nombre': 'Multimetro', 'fecha_adquisicion': '2023-01-10',
        })
        self.assertContains(self.client.get(f'/inventario/equipo/{equipo.id}/historial/'), '10/01/2023')

    def test_importar_lee_fechas_de_celda_y_texto(self):
        wb = Workbook()
        ws = wb.active
        ws.title = 'Equipos'
        ws.append(['Código', 'Nombre', 'Fecha de adquisición'])
        ws.append(['IM-1', 'Osciloscopio', datetime(2015, 5, 20)])
        ws.append(['IM-2', 'Router', '03-02-' + str(timezone.localdate().year - 1)])
        salida = BytesIO()
        wb.save(salida)
        self.client.post('/inventario/importar/', {'archivo': SimpleUploadedFile('i.xlsx', salida.getvalue())})
        viejo, nuevo = Equipo.objects.order_by('codigo_inventario')
        self.assertEqual((viejo.fecha_adquisicion, viejo.estado), (date(2015, 5, 20), Equipo.Estado.PENDIENTE_BAJA))
        self.assertEqual((nuevo.fecha_adquisicion.month, nuevo.estado), (2, Equipo.Estado.DISPONIBLE))

    def test_importacion_envia_un_solo_aviso(self):
        wb = Workbook()
        ws = wb.active
        ws.title = 'Equipos'
        ws.append(['Código', 'Nombre', 'Fecha de adquisición'])
        for i in range(3):
            ws.append([f'IM-{i}', 'Router antiguo', datetime(2015, 1, 1 + i)])
        salida = BytesIO()
        wb.save(salida)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post('/inventario/importar/', {'archivo': SimpleUploadedFile('i.xlsx', salida.getvalue())})
        self.assertEqual(Equipo.objects.filter(estado=Equipo.Estado.PENDIENTE_BAJA).count(), 3)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Equipos pendientes de baja (3)')
