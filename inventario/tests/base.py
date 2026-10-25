"""
Utilidades comunes para los tests del sistema de inventario LEICA.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from inventario.models import Equipo, Insumo, Solicitud, SolicitudItem, Usuario

# Los tests no deben depender de que 'collectstatic' este al dia.
STORAGES_TEST = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
}


@override_settings(
    STORAGES=STORAGES_TEST,
    GEMINI_API_KEY='',
    # Hasher rapido: PBKDF2 hace muy lenta la creacion de usuarios en cada clase de test.
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    SECURE_SSL_REDIRECT=False,
)
class LeicaTestCase(TestCase):
    """Base con un usuario por rol y helpers para crear datos de prueba."""

    @classmethod
    def setUpTestData(cls):
        cls.encargado = cls.crear_usuario('encargado', Usuario.Rol.ENCARGADO_LABORATORIO, is_staff=True)
        cls.calidad = cls.crear_usuario('calidad', Usuario.Rol.CONTROL_CALIDAD)
        cls.director = cls.crear_usuario('director', Usuario.Rol.DIRECTOR_CARRERA)
        cls.docente = cls.crear_usuario('docente', Usuario.Rol.DOCENTE)
        cls.comite = cls.crear_usuario('comite', Usuario.Rol.COMITE_EJECUTIVO)
        cls.estudiante = cls.crear_usuario('estudiante', Usuario.Rol.ESTUDIANTE, seccion='TIN-401')

    @staticmethod
    def crear_usuario(nombre, rol, **extra):
        return Usuario.objects.create_user(
            username=nombre,
            email=f'{nombre}@inacapmail.cl',
            password='Leica2026!',
            rol=rol,
            **extra,
        )

    @staticmethod
    def crear_equipo(codigo='LTV-001', nombre='Multimetro', valor=Decimal('1000.00'), **extra):
        return Equipo.objects.create(
            codigo_inventario=codigo, nombre=nombre, valor_adquisicion=valor, **extra,
        )

    @staticmethod
    def crear_insumo(nombre='Protoboard', cantidad=10, tipo=Insumo.Tipo.RENOVABLE, umbral=2, **extra):
        return Insumo.objects.create(
            nombre=nombre, tipo=tipo, cantidad_total=cantidad,
            cantidad_disponible=cantidad, umbral_minimo=umbral, **extra,
        )

    @staticmethod
    def crear_solicitud(solicitante, equipos=(), insumos=(), inicio=None, fin=None, estado=None):
        """insumos es una lista de tuplas (insumo, cantidad)."""
        inicio = inicio or timezone.now() + timedelta(hours=1)
        fin = fin or inicio + timedelta(hours=2)
        solicitud = Solicitud.objects.create(
            solicitante=solicitante, horario_inicio=inicio, horario_fin=fin,
            estado=estado or Solicitud.EstadoSolicitud.PENDIENTE,
        )
        for equipo in equipos:
            SolicitudItem.objects.create(solicitud=solicitud, equipo=equipo, cantidad=1)
        for insumo, cantidad in insumos:
            SolicitudItem.objects.create(solicitud=solicitud, insumo=insumo, cantidad=cantidad)
        return solicitud

    def accion_solicitud(self, solicitud, accion, **extra):
        return self.client.post('/solicitudes/', {'solicitud_id': solicitud.id, 'accion': accion, **extra})
