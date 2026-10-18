import importlib
from decimal import Decimal

from django.apps import apps as django_apps

from inventario import auditoria
from inventario.models import Equipo, HistorialEquipo, Mantenimiento, Movimiento, Solicitud, Usuario
from .base import LeicaTestCase


class QREquipoTests(LeicaTestCase):

    def test_genera_svg_localmente(self):
        equipo = self.crear_equipo('QR-1')
        self.client.force_login(self.encargado)
        r = self.client.get(f'/inventario/equipo/{equipo.id}/qr/')
        self.assertEqual(r['Content-Type'], 'image/svg+xml')
        self.assertTrue(r.content.startswith(b'<?xml'))
        self.assertIn(b'<svg', r.content)
        self.assertNotIn('Content-Disposition', r)

    def test_descarga(self):
        equipo = self.crear_equipo('QR-2')
        self.client.force_login(self.calidad)
        r = self.client.get(f'/inventario/equipo/{equipo.id}/qr/?descargar=1')
        self.assertEqual(r['Content-Disposition'], 'attachment; filename="qr_QR-2.svg"')

    def test_solo_roles_de_inventario(self):
        equipo = self.crear_equipo()
        self.client.force_login(self.estudiante)
        self.assertEqual(self.client.get(f'/inventario/equipo/{equipo.id}/qr/').status_code, 403)

    def test_inventario_no_usa_servicios_externos(self):
        self.crear_equipo()
        self.client.force_login(self.encargado)
        html = self.client.get('/inventario/').content.decode()
        self.assertNotIn('qrserver', html)
        self.assertIn('data-qr="/inventario/equipo/', html)


class AuditoriaEquipoTests(LeicaTestCase):

    def setUp(self):
        self.client.force_login(self.encargado)

    def historial(self, codigo):
        return list(HistorialEquipo.objects.filter(codigo_inventario=codigo).order_by('id'))

    def test_crear_registra_todos_los_datos(self):
        self.client.post('/inventario/?tab=equipos', {'codigo_inventario': 'AU-1', 'nombre': 'Router', 'valor_adquisicion': '500'})
        h, = self.historial('AU-1')
        self.assertEqual((h.accion, h.usuario), (HistorialEquipo.Accion.CREADO, self.encargado))
        self.assertEqual(h.cambios['nombre'], [None, 'Router'])
        self.assertEqual(h.cambios['estado'], [None, 'disponible'])

    def test_editar_registra_solo_lo_que_cambio(self):
        e = self.crear_equipo('AU-2', 'Viejo', ubicacion='Sala 1')
        self.client.post(f'/inventario/equipo/{e.id}/editar/', {
            'codigo_inventario': 'AU-2', 'nombre': 'Nuevo', 'ubicacion': 'Sala 1', 'valor_adquisicion': '1000.00',
        })
        h, = self.historial('AU-2')
        self.assertEqual(h.accion, HistorialEquipo.Accion.EDITADO)
        self.assertEqual(h.cambios, {'nombre': ['Viejo', 'Nuevo']})

    def test_editar_sin_cambios_no_registra(self):
        e = self.crear_equipo('AU-3', 'Igual')
        self.client.post(f'/inventario/equipo/{e.id}/editar/', {
            'codigo_inventario': 'AU-3', 'nombre': 'Igual', 'valor_adquisicion': '1000.00',
        })
        self.assertEqual(self.historial('AU-3'), [])

    def test_eliminar_conserva_el_registro(self):
        e = self.crear_equipo('AU-4', 'Para borrar')
        self.client.post(f'/inventario/equipo/{e.id}/eliminar/')
        h, = self.historial('AU-4')
        self.assertEqual((h.accion, h.equipo), (HistorialEquipo.Accion.ELIMINADO, None))
        self.assertEqual(h.cambios['nombre'], ['Para borrar', None])

    def test_eliminacion_fallida_no_deja_registro(self):
        e = self.crear_equipo('AU-5')
        self.crear_solicitud(self.estudiante, equipos=[e], estado='devuelta')
        self.client.post(f'/inventario/equipo/{e.id}/eliminar/')
        self.assertEqual(self.historial('AU-5'), [])

    def test_prestamo_registra_entrega_y_devolucion(self):
        e = self.crear_equipo('AU-6')
        s = self.crear_solicitud(self.estudiante, equipos=[e], estado=Solicitud.EstadoSolicitud.APROBADA)
        self.accion_solicitud(s, 'entregar')
        self.accion_solicitud(s, 'devolver', estado_equipo='dañado')
        entrega, devolucion = self.historial('AU-6')
        self.assertEqual(entrega.cambios, {'estado': ['disponible', 'prestado']})
        self.assertIn(f'Entrega de la solicitud #{s.id}', entrega.detalle)
        self.assertEqual(devolucion.cambios, {'estado': ['prestado', 'en_mantenimiento']})
        self.assertIn('dañado', devolucion.detalle)

    def test_mantenimiento_y_panel_admin_registran_estado(self):
        e = self.crear_equipo('AU-7', valor=Decimal('1000'))
        self.client.post('/mantenimiento/', {'equipo_id': e.id, 'falla_descrita': 'x', 'costo_cotizado': '100'})
        mant = Mantenimiento.objects.get()
        self.client.post('/mantenimiento/', {'mant_id': mant.id, 'accion_mant': 'completar_reparacion'})
        self.client.post('/panel-admin/', {'accion': 'cambiar_estado_equipo', 'equipo_id': e.id, 'nuevo_estado': 'fuera_servicio'})
        estados = [h.cambios['estado'] for h in self.historial('AU-7')]
        self.assertEqual(estados, [['disponible', 'en_mantenimiento'], ['en_mantenimiento', 'disponible'],
                                   ['disponible', 'fuera_servicio']])

    def test_pagina_de_historial(self):
        e = self.crear_equipo('AU-8', 'Viejo')
        self.client.post(f'/inventario/equipo/{e.id}/editar/', {
            'codigo_inventario': 'AU-8', 'nombre': '<b>Nuevo</b>', 'valor_adquisicion': '1000.00',
        })
        r = self.client.get(f'/inventario/equipo/{e.id}/historial/')
        self.assertContains(r, 'Historial de cambios')
        self.assertContains(r, '&lt;b&gt;Nuevo&lt;/b&gt;')
        self.assertContains(r, 'historial-editado')
        self.client.force_login(self.estudiante)
        self.assertEqual(self.client.get(f'/inventario/equipo/{e.id}/historial/').status_code, 403)

    def test_borrado_masivo_desde_el_admin_queda_registrado(self):
        admin = self.crear_usuario('admin', Usuario.Rol.ENCARGADO_LABORATORIO, is_staff=True, is_superuser=True)
        e1, e2 = self.crear_equipo('AU-9'), self.crear_equipo('AU-10')
        self.client.force_login(admin)
        self.client.post('/admin/inventario/equipo/', {
            'action': 'delete_selected', '_selected_action': [e1.id, e2.id], 'post': 'yes',
        })
        self.assertFalse(Equipo.objects.filter(id__in=[e1.id, e2.id]).exists())
        for codigo in ('AU-9', 'AU-10'):
            h, = self.historial(codigo)
            self.assertEqual(h.accion, HistorialEquipo.Accion.ELIMINADO)

    def test_detalle_largo_se_recorta(self):
        e = self.crear_equipo('AU-11')
        e.nombre = 'Otro'
        h = auditoria.registrar(e, self.encargado, HistorialEquipo.Accion.EDITADO, {**auditoria.foto(e), 'nombre': 'X'}, 'x' * 400)
        self.assertEqual(len(h.detalle), 255)


class MigracionAtrasadasTests(LeicaTestCase):

    def test_atrasadas_antiguas_ya_devueltas_pasan_a_devuelta_con_atraso(self):
        modulo = importlib.import_module('inventario.migrations.0007_atrasadas_devueltas')
        devuelta = self.crear_solicitud(self.estudiante, estado=Solicitud.EstadoSolicitud.ATRASADA)
        Movimiento.objects.create(solicitud=devuelta, tipo=Movimiento.TipoMovimiento.DEVOLUCION, responsable=self.encargado)
        sin_devolver = self.crear_solicitud(self.estudiante, estado=Solicitud.EstadoSolicitud.ATRASADA)
        modulo.convertir_atrasadas_devueltas(django_apps, None)
        devuelta.refresh_from_db()
        sin_devolver.refresh_from_db()
        self.assertEqual(devuelta.estado, Solicitud.EstadoSolicitud.DEVUELTA_ATRASO)
        self.assertEqual(sin_devolver.estado, Solicitud.EstadoSolicitud.ATRASADA)
