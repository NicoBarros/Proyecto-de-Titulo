"""
RF-10: Mantenimiento y regla del 70% (costo de reparacion vs valor de adquisicion).
"""
from decimal import Decimal
from unittest import expectedFailure

from inventario.models import Equipo, Mantenimiento
from .base import LeicaTestCase


class ReglaDel70Tests(LeicaTestCase):

    def setUp(self):
        self.client.force_login(self.encargado)

    def diagnosticar(self, equipo, costo):
        return self.client.post('/mantenimiento/', {
            'equipo_id': equipo.id, 'falla_descrita': 'No enciende', 'costo_cotizado': costo,
        })

    def test_costo_menor_al_70_sugiere_reparar(self):
        e = self.crear_equipo(valor=Decimal('1000'))
        self.diagnosticar(e, '600')
        m = Mantenimiento.objects.get()
        self.assertEqual(m.decision, Mantenimiento.Decision.REPARAR)
        self.assertEqual(m.porcentaje_costo, Decimal('0.6000'))
        e.refresh_from_db()
        self.assertEqual(e.estado, Equipo.Estado.EN_MANTENIMIENTO)
        self.assertEqual(m.reportado_por, self.encargado)

    @expectedFailure
    def test_bug_redondeo_antes_de_comparar(self):
        """69.999% se redondea a 0.7000 ANTES de comparar con 0.70 y termina sugiriendo dar de baja."""
        e = self.crear_equipo(valor=Decimal('1000'))
        self.diagnosticar(e, '699.99')
        self.assertEqual(Mantenimiento.objects.get().decision, Mantenimiento.Decision.REPARAR)

    def test_costo_igual_al_70_sugiere_dar_baja(self):
        e = self.crear_equipo(valor=Decimal('1000'))
        self.diagnosticar(e, '700')
        self.assertEqual(Mantenimiento.objects.get().decision, Mantenimiento.Decision.DAR_BAJA)

    def test_costo_mayor_al_70_sugiere_dar_baja(self):
        e = self.crear_equipo(valor=Decimal('1000'))
        self.diagnosticar(e, '950')
        m = Mantenimiento.objects.get()
        self.assertEqual(m.decision, Mantenimiento.Decision.DAR_BAJA)
        self.assertEqual(m.porcentaje_costo, Decimal('0.9500'))

    def test_sin_valor_adquisicion_sugiere_reparar(self):
        e = self.crear_equipo(valor=None)
        self.diagnosticar(e, '500')
        m = Mantenimiento.objects.get()
        self.assertIsNone(m.porcentaje_costo)
        self.assertEqual(m.decision, Mantenimiento.Decision.REPARAR)

    def test_formulario_incompleto_no_crea(self):
        e = self.crear_equipo()
        self.client.post('/mantenimiento/', {'equipo_id': e.id})
        self.assertFalse(Mantenimiento.objects.exists())


class ResolucionMantenimientoTests(LeicaTestCase):

    def setUp(self):
        self.client.force_login(self.calidad)
        self.equipo = self.crear_equipo(estado=Equipo.Estado.EN_MANTENIMIENTO)
        self.mant = Mantenimiento.objects.create(equipo=self.equipo, costo_cotizado=Decimal('100'))

    def resolver(self, accion):
        self.client.post('/mantenimiento/', {'mant_id': self.mant.id, 'accion_mant': accion})
        self.mant.refresh_from_db(); self.equipo.refresh_from_db()

    def test_completar_reparacion_libera_equipo(self):
        self.resolver('completar_reparacion')
        self.assertEqual(self.mant.decision, Mantenimiento.Decision.COMPLETADO)
        self.assertIsNotNone(self.mant.fecha_resolucion)
        self.assertEqual(self.equipo.estado, Equipo.Estado.DISPONIBLE)

    def test_dar_baja_deja_fuera_de_servicio(self):
        self.resolver('dar_baja')
        self.assertEqual(self.mant.decision, Mantenimiento.Decision.DAR_BAJA)
        self.assertEqual(self.equipo.estado, Equipo.Estado.FUERA_SERVICIO)

    def test_reparar_mantiene_en_mantenimiento(self):
        self.resolver('reparar')
        self.assertEqual(self.mant.decision, Mantenimiento.Decision.REPARAR)
        self.assertEqual(self.equipo.estado, Equipo.Estado.EN_MANTENIMIENTO)
