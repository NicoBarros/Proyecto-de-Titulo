
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.contrib.auth.models import AbstractUser
from django.utils import timezone


class Usuario(AbstractUser):

    class Rol(models.TextChoices):
        ESTUDIANTE = 'estudiante', 'Estudiante'
        DOCENTE = 'docente', 'Docente'
        DIRECTOR_CARRERA = 'director_carrera', 'Director de Carrera'
        ENCARGADO_LABORATORIO = 'encargado_laboratorio', 'Encargado de Laboratorio'
        CONTROL_CALIDAD = 'control_calidad', 'Control de Calidad'
        COMITE_EJECUTIVO = 'comite_ejecutivo', 'Comité Ejecutivo'

    rol = models.CharField(
        max_length=30,
        choices=Rol.choices,
        default=Rol.ESTUDIANTE,
        verbose_name='Rol institucional',
    )
    seccion = models.CharField(
        max_length=30, blank=True, null=True,
        help_text='Para estudiantes (usado en bloqueos RF-09)',
    )
    bloqueado_hasta = models.DateTimeField(
        blank=True, null=True,
        help_text='RF-09: fecha hasta la cual el usuario esta bloqueado',
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    email = models.EmailField(unique=True)

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return f'{self.get_full_name() or self.username} ({self.get_rol_display()})'

    def esta_bloqueado(self):
        if self.bloqueado_hasta and self.bloqueado_hasta > timezone.now():
            return True
        return False

    def tiene_atrasos(self):
        return Solicitud.objects.filter(estado=Solicitud.EstadoSolicitud.ATRASADA).filter(
            Q(en_representacion_de=self) | Q(solicitante=self, en_representacion_de__isnull=True)
        ).exists()

    ROLES_ESCRITURA_INVENTARIO = [Rol.ENCARGADO_LABORATORIO, Rol.CONTROL_CALIDAD]

    ROLES_APROBADORES = [Rol.ENCARGADO_LABORATORIO, Rol.CONTROL_CALIDAD, Rol.DIRECTOR_CARRERA]
    ROLES_REPRESENTANTES = [Rol.DOCENTE, Rol.DIRECTOR_CARRERA, Rol.ENCARGADO_LABORATORIO, Rol.CONTROL_CALIDAD]
    ROLES_REPORTES = [Rol.ENCARGADO_LABORATORIO, Rol.CONTROL_CALIDAD, Rol.DIRECTOR_CARRERA, Rol.COMITE_EJECUTIVO]

class Equipo(models.Model):

    class Estado(models.TextChoices):
        DISPONIBLE = 'disponible', 'Disponible'
        PRESTADO = 'prestado', 'Prestado'
        EN_MANTENIMIENTO = 'en_mantenimiento', 'En mantenimiento'
        FUERA_SERVICIO = 'fuera_servicio', 'Fuera de servicio'

    codigo_inventario = models.CharField(
        max_length=50, unique=True,
        verbose_name='Código de inventario',
    )
    nombre = models.CharField(max_length=200)
    modelo = models.CharField(max_length=200, blank=True, null=True)
    especificaciones = models.TextField(blank=True, null=True)
    ubicacion = models.CharField(max_length=200, blank=True, null=True, verbose_name='Ubicación')
    estado = models.CharField(
        max_length=20, choices=Estado.choices, default=Estado.DISPONIBLE,
    )
    valor_adquisicion = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True,
        validators=[MinValueValidator(0)],
        verbose_name='Valor de adquisición ($)',
    )
    version = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Equipo'
        verbose_name_plural = 'Equipos'
        ordering = ['nombre']

    def __str__(self):
        return f'{self.codigo_inventario} — {self.nombre}'

class Insumo(models.Model):

    class Tipo(models.TextChoices):
        RENOVABLE = 'renovable', 'Renovable'
        PERECIBLE = 'perecible', 'Perecible'

    nombre = models.CharField(max_length=200, unique=True)
    categoria = models.CharField(max_length=100, blank=True, null=True, verbose_name='Categoría')
    tipo = models.CharField(
        max_length=10, choices=Tipo.choices, default=Tipo.PERECIBLE,
        help_text='Hallazgo entrevista (Anexo 6, #16): renovable vuelve al stock al devolver',
    )
    cantidad_total = models.PositiveIntegerField(default=0)
    cantidad_disponible = models.PositiveIntegerField(default=0)
    umbral_minimo = models.PositiveIntegerField(
        default=0,
        help_text='Aviso de stock bajo cuando cantidad_disponible <= umbral_minimo',
    )
    version = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Insumo'
        verbose_name_plural = 'Insumos'
        ordering = ['nombre']

    def __str__(self):
        return f'{self.nombre} ({self.cantidad_disponible}/{self.cantidad_total})'

    @property
    def bajo_stock(self):
        return self.cantidad_disponible <= self.umbral_minimo

class Solicitud(models.Model):

    class EstadoSolicitud(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente'
        APROBADA = 'aprobada', 'Aprobada'
        RECHAZADA = 'rechazada', 'Rechazada'
        ENTREGADA = 'entregada', 'Entregada'
        DEVUELTA = 'devuelta', 'Devuelta'
        ATRASADA = 'atrasada', 'Atrasada'
        DEVUELTA_ATRASO = 'devuelta_atraso', 'Devuelta con atraso'
        CANCELADA = 'cancelada', 'Cancelada'

    class LugarUso(models.TextChoices):
        DENTRO_SEDE = 'dentro_sede', 'Dentro de sede'
        FUERA_SEDE = 'fuera_sede', 'Fuera de sede'

    solicitante = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name='solicitudes',
    )
    en_representacion_de = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, blank=True, null=True,
        related_name='solicitudes_representadas',
        help_text='Si el solicitante es docente/director actuando por un estudiante',
    )
    lugar_uso = models.CharField(
        max_length=15, choices=LugarUso.choices, default=LugarUso.DENTRO_SEDE,
        help_text='Hallazgo entrevista #7',
    )
    justificacion = models.TextField(blank=True, null=True, verbose_name='Justificación')
    horario_inicio = models.DateTimeField()
    horario_fin = models.DateTimeField()
    estado = models.CharField(
        max_length=15, choices=EstadoSolicitud.choices, default=EstadoSolicitud.PENDIENTE,
    )
    aprobado_por = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, blank=True, null=True,
        related_name='solicitudes_aprobadas',
    )
    fecha_aprobacion = models.DateTimeField(blank=True, null=True)
    recordatorio_enviado = models.DateTimeField(blank=True, null=True)
    aviso_atraso_enviado = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    ESTADOS_EN_PRESTAMO = [EstadoSolicitud.ENTREGADA, EstadoSolicitud.ATRASADA]

    class Meta:
        verbose_name = 'Solicitud'
        verbose_name_plural = 'Solicitudes'
        ordering = ['-created_at']

    @classmethod
    def marcar_atrasadas(cls):
        return cls.objects.filter(
            estado=cls.EstadoSolicitud.ENTREGADA, horario_fin__lt=timezone.now(),
        ).update(estado=cls.EstadoSolicitud.ATRASADA)

    def __str__(self):
        return f'Solicitud #{self.pk} — {self.get_estado_display()}'

    @property
    def beneficiario(self):
        return self.en_representacion_de or self.solicitante

    def destinatarios(self):
        return sorted({u.email for u in (self.solicitante, self.en_representacion_de) if u and u.email})


class SolicitudItem(models.Model):

    class EstadoDevolucion(models.TextChoices):
        EXCELENTE = 'excelente', 'Excelente'
        BUENO = 'bueno', 'Bueno'
        DANADO = 'dañado', 'Dañado'
        INSERVIBLE = 'inservible', 'Inservible'

    ESTADOS_CON_FALLA = [EstadoDevolucion.DANADO, EstadoDevolucion.INSERVIBLE]

    solicitud = models.ForeignKey(
        Solicitud, on_delete=models.CASCADE, related_name='items',
    )
    equipo = models.ForeignKey(
        Equipo, on_delete=models.PROTECT, blank=True, null=True,
    )
    insumo = models.ForeignKey(
        Insumo, on_delete=models.PROTECT, blank=True, null=True,
    )
    cantidad = models.PositiveIntegerField(default=1)
    estado_devolucion = models.CharField(
        max_length=20, choices=EstadoDevolucion.choices, blank=True, default='',
        verbose_name='Estado al devolver',
    )

    class Meta:
        verbose_name = 'Ítem de solicitud'
        verbose_name_plural = 'Ítems de solicitud'

    def __str__(self):
        nombre = self.equipo.nombre if self.equipo else self.insumo.nombre
        return f'{nombre} x{self.cantidad}'

class Movimiento(models.Model):

    class TipoMovimiento(models.TextChoices):
        ENTREGA = 'entrega', 'Entrega'
        DEVOLUCION = 'devolucion', 'Devolución'

    solicitud = models.ForeignKey(
        Solicitud, on_delete=models.CASCADE, related_name='movimientos',
    )
    tipo = models.CharField(max_length=10, choices=TipoMovimiento.choices)
    fecha = models.DateTimeField(auto_now_add=True)
    responsable = models.ForeignKey(
        Usuario, on_delete=models.PROTECT, related_name='movimientos_responsable',
    )
    estado_equipo = models.CharField(
        max_length=20, blank=True, null=True,
        help_text='RF-08 / hallazgo #13: condicion al devolver',
    )
    observacion = models.TextField(blank=True, null=True, verbose_name='Observación')

    class Meta:
        verbose_name = 'Movimiento'
        verbose_name_plural = 'Movimientos'
        ordering = ['fecha']

class Bloqueo(models.Model):

    usuario = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name='bloqueos',
    )
    seccion = models.CharField(max_length=30, blank=True, null=True)
    solicitud = models.ForeignKey(
        Solicitud, on_delete=models.SET_NULL, blank=True, null=True,
    )
    fecha_inicio = models.DateTimeField(auto_now_add=True)
    fecha_fin = models.DateTimeField(
        help_text='Maximo 1 semana segun entrevista (hallazgo #10)',
    )
    motivo = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = 'Bloqueo'
        verbose_name_plural = 'Bloqueos'

class Mantenimiento(models.Model):

    class Decision(models.TextChoices):
        REPARAR = 'reparar', 'Reparar'
        DAR_BAJA = 'dar_baja', 'Dar de baja'
        PENDIENTE = 'pendiente', 'Pendiente'
        COMPLETADO = 'completado', 'Reparación completada'

    equipo = models.ForeignKey(
        Equipo, on_delete=models.PROTECT, related_name='mantenimientos',
    )
    falla_descrita = models.TextField(blank=True, null=True)
    costo_cotizado = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True,
    )
    porcentaje_costo = models.DecimalField(
        max_digits=10, decimal_places=4, blank=True, null=True,
        help_text='costo_cotizado / valor_adquisicion',
    )
    decision = models.CharField(
        max_length=20, choices=Decision.choices, default=Decision.PENDIENTE,
    )
    fecha_diagnostico = models.DateTimeField(auto_now_add=True)
    fecha_resolucion = models.DateTimeField(blank=True, null=True)
    reportado_por = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, blank=True, null=True,
    )

    class Meta:
        verbose_name = 'Mantenimiento'
        verbose_name_plural = 'Mantenimientos'
        ordering = ['-fecha_diagnostico']

    def __str__(self):
        return f'Mantenimiento #{self.pk} — {self.equipo}'
        
class Migracion(models.Model):

    archivo_origen = models.CharField(max_length=255, blank=True, null=True)
    filas_totales = models.PositiveIntegerField(default=0)
    filas_importadas = models.PositiveIntegerField(default=0)
    filas_con_error = models.PositiveIntegerField(default=0)
    detalle_errores = models.TextField(blank=True, null=True)
    ejecutado_por = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, blank=True, null=True,
    )
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Migración'
        verbose_name_plural = 'Migraciones'
        ordering = ['-fecha']

    def __str__(self):
        return f'Migración #{self.pk} — {self.archivo_origen}'


class HistorialEquipo(models.Model):

    class Accion(models.TextChoices):
        CREADO = 'creado', 'Creado'
        EDITADO = 'editado', 'Editado'
        ESTADO = 'estado', 'Cambio de estado'
        IMPORTADO = 'importado', 'Importado'
        ELIMINADO = 'eliminado', 'Eliminado'

    equipo = models.ForeignKey(
        Equipo, on_delete=models.SET_NULL, blank=True, null=True, related_name='historial',
    )
    codigo_inventario = models.CharField(max_length=50)
    usuario = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, blank=True, null=True, related_name='cambios_equipos',
    )
    fecha = models.DateTimeField(auto_now_add=True)
    accion = models.CharField(max_length=15, choices=Accion.choices)
    cambios = models.JSONField(default=dict, blank=True)
    detalle = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        verbose_name = 'Historial de equipo'
        verbose_name_plural = 'Historial de equipos'
        ordering = ['-fecha', '-id']

    def __str__(self):
        return f'{self.codigo_inventario} — {self.get_accion_display()} ({self.fecha:%d/%m/%Y %H:%M})'


class EventoSeguridad(models.Model):

    class Tipo(models.TextChoices):
        INICIO_SESION = 'inicio_sesion', 'Inicio de sesión'
        CIERRE_SESION = 'cierre_sesion', 'Cierre de sesión'
        INTENTO_FALLIDO = 'intento_fallido', 'Intento de inicio fallido'
        BLOQUEO = 'bloqueo', 'Bloqueo por intentos fallidos'
        ACCESO_DENEGADO = 'acceso_denegado', 'Acceso denegado'
        CAMBIO_CUENTA = 'cambio_cuenta', 'Cambio de cuenta'

    fecha = models.DateTimeField(auto_now_add=True, db_index=True)
    tipo = models.CharField(max_length=20, choices=Tipo.choices, db_index=True)
    usuario = models.ForeignKey(
        Usuario, on_delete=models.SET_NULL, blank=True, null=True, related_name='eventos_seguridad',
    )
    identificador = models.CharField(max_length=254, blank=True, default='')
    ip = models.GenericIPAddressField(blank=True, null=True)
    ruta = models.CharField(max_length=255, blank=True, default='')
    agente = models.CharField(max_length=255, blank=True, default='')
    detalle = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        verbose_name = 'Evento de seguridad'
        verbose_name_plural = 'Eventos de seguridad'
        ordering = ['-fecha', '-id']

    def __str__(self):
        return f'{self.get_tipo_display()} — {self.identificador or "anónimo"} ({self.fecha:%d/%m/%Y %H:%M})'
