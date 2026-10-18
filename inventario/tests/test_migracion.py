"""
RF-14: Migracion (importacion) de inventario desde CSV.
"""
import json

from django.core.files.uploadedfile import SimpleUploadedFile

from inventario.models import Equipo, Insumo, Migracion
from .base import LeicaTestCase

CABECERA = 'tipo,codigo_inventario,nombre,modelo,especificaciones,ubicacion,estado,valor_adquisicion,categoria,tipo_insumo,cantidad\n'


class MigracionCSVTests(LeicaTestCase):

    def setUp(self):
        self.client.force_login(self.encargado)

    def subir(self, contenido, nombre='inventario.csv'):
        archivo = SimpleUploadedFile(nombre, contenido.encode('utf-8'), content_type='text/csv')
        return self.client.post('/migracion/', {'archivo': archivo})

    def test_importa_equipos_e_insumos(self):
        self.subir(CABECERA
                   + 'equipo,CSV-1,Osciloscopio,TBS1052B,50MHz,Sala 1,disponible,1500.50,,,\n'
                   + 'insumo,,Cables,,,,,,Cables,renovable,25\n')
        e = Equipo.objects.get(codigo_inventario='CSV-1')
        self.assertEqual(str(e.valor_adquisicion), '1500.50')
        i = Insumo.objects.get(nombre='Cables')
        self.assertEqual((i.cantidad_total, i.cantidad_disponible, i.tipo), (25, 25, 'renovable'))
        m = Migracion.objects.get()
        self.assertEqual((m.filas_totales, m.filas_importadas, m.filas_con_error), (2, 2, 0))
        self.assertEqual(m.archivo_origen, 'inventario.csv')
        self.assertEqual(m.ejecutado_por, self.encargado)

    def test_equipo_existente_se_actualiza(self):
        self.crear_equipo('CSV-1', 'Nombre viejo')
        self.subir(CABECERA + 'equipo,CSV-1,Nombre nuevo,,,,disponible,,,,\n')
        self.assertEqual(Equipo.objects.get(codigo_inventario='CSV-1').nombre, 'Nombre nuevo')
        self.assertEqual(Equipo.objects.count(), 1)

    def test_filas_con_error_se_registran_y_el_resto_se_importa(self):
        self.subir(CABECERA
                   + 'equipo,,SinCodigo,,,,,,,,\n'
                   + 'otro,X,Y,,,,,,,,\n'
                   + 'insumo,,Malo,,,,,,,,no_es_numero\n'
                   + 'equipo,OK-1,Bueno,,,,disponible,,,,\n')
        m = Migracion.objects.get()
        self.assertEqual((m.filas_totales, m.filas_importadas, m.filas_con_error), (4, 1, 3))
        errores = json.loads(m.detalle_errores)
        self.assertTrue(errores[0].startswith('Fila 2:'))
        self.assertTrue(Equipo.objects.filter(codigo_inventario='OK-1').exists())

    def test_sin_archivo_no_registra_migracion(self):
        self.client.post('/migracion/', {})
        self.assertFalse(Migracion.objects.exists())

    def test_archivo_no_utf8(self):
        archivo = SimpleUploadedFile('x.csv', 'tipo,nombre\nequipo,Ñandú\n'.encode('latin-1'))
        r = self.client.post('/migracion/', {'archivo': archivo})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Migracion.objects.exists())

    def test_exportar_e_importar_es_ida_y_vuelta(self):
        self.crear_equipo('RT-1', 'Router')
        csv_exportado = self.client.get('/inventario/exportar/').content.decode()
        Equipo.objects.all().delete()
        self.subir(csv_exportado)
        self.assertTrue(Equipo.objects.filter(codigo_inventario='RT-1', nombre='Router').exists())

    def test_reimportar_insumo_no_lo_duplica(self):
        fila = CABECERA + 'insumo,,Cables,,,,,,Cables,renovable,25\n'
        self.subir(fila)
        self.subir(fila)
        self.assertEqual(Insumo.objects.filter(nombre='Cables').count(), 1)

    def test_estado_invalido_es_error(self):
        self.subir(CABECERA + 'equipo,BAD-1,Raro,,,,roto_total,,,,\n')
        self.assertFalse(Equipo.objects.filter(codigo_inventario='BAD-1').exists())

    def test_acepta_csv_con_bom_de_excel(self):
        self.subir('\ufeff' + CABECERA + 'equipo,BOM-1,Router,,,,,,,,\n')
        self.assertTrue(Equipo.objects.filter(codigo_inventario='BOM-1').exists())

    def test_reimportar_insumo_respeta_unidades_prestadas(self):
        insumo = self.crear_insumo('Cables', cantidad=25)
        Insumo.objects.filter(id=insumo.id).update(cantidad_disponible=20)  # 5 prestados
        self.subir(CABECERA + 'insumo,,Cables,,,,,,Cables,renovable,30\n')
        insumo.refresh_from_db()
        self.assertEqual((insumo.cantidad_total, insumo.cantidad_disponible), (30, 25))

    def test_sin_estado_no_cambia_equipo_prestado(self):
        self.crear_equipo('PR-1', 'Router', estado=Equipo.Estado.PRESTADO)
        self.subir(CABECERA + 'equipo,PR-1,Router nuevo,,,,,,,,\n')
        e = Equipo.objects.get(codigo_inventario='PR-1')
        self.assertEqual((e.nombre, e.estado), ('Router nuevo', Equipo.Estado.PRESTADO))

    def test_columnas_vacias_no_borran_stock_ni_tipo(self):
        insumo = self.crear_insumo('Cables', cantidad=25, tipo=Insumo.Tipo.RENOVABLE)
        self.subir(CABECERA + 'insumo,,Cables,,,,,,Nueva categoria,,\n')
        insumo.refresh_from_db()
        self.assertEqual((insumo.cantidad_total, insumo.cantidad_disponible, insumo.tipo, insumo.categoria),
                         (25, 25, Insumo.Tipo.RENOVABLE, 'Nueva categoria'))

    def test_no_baja_el_total_por_debajo_de_lo_prestado(self):
        insumo = self.crear_insumo('Cables', cantidad=10)
        Insumo.objects.filter(id=insumo.id).update(cantidad_disponible=2)  # 8 prestados
        self.subir(CABECERA + 'insumo,,Cables,,,,,,,,5\n')
        insumo.refresh_from_db()
        self.assertEqual((insumo.cantidad_total, insumo.cantidad_disponible), (10, 2))
        self.assertEqual(Migracion.objects.get().filas_con_error, 1)

    def test_valor_adquisicion_invalido_da_mensaje_legible(self):
        self.subir(CABECERA + 'equipo,V-1,Router,,,,,1.500.000,,,\n')
        errores = json.loads(Migracion.objects.get().detalle_errores)
        self.assertIn('valor_adquisicion "1.500.000" no es un número válido', errores[0])
