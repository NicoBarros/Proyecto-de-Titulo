
from django.db import models
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
        """RF-09: verifica si la cuenta esta bloqueada."""
        if self.bloqueado_hasta and self.bloqueado_hasta > timezone.now():
            return True
        return False

    ROLES_ESCRITURA_INVENTARIO = [Rol.ENCARGADO_LABORATORIO, Rol.CONTROL_CALIDAD]

    ROLES_APROBADORES = [Rol.DOCENTE, Rol.DIRECTOR_CARRERA, Rol.ENCARGADO_LABORATORIO]

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
    """Insumo gestionado por cantidad (no por codigo individual)."""

    class Tipo(models.TextChoices):
        RENOVABLE = 'renovable', 'Renovable'
        PERECIBLE = 'perecible', 'Perecible'

    nombre = models.CharField(max_length=200)
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
    """Solicitud de prestamo de equipos/insumos."""

    class EstadoSolicitud(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente'
        APROBADA = 'aprobada', 'Aprobada'
        RECHAZADA = 'rechazada', 'Rechazada'
        ENTREGADA = 'entregada', 'Entregada'
        DEVUELTA = 'devuelta', 'Devuelta'
        ATRASADA = 'atrasada', 'Atrasada'
        CANCELADA = 'cancelada', 'Cancelada'

    class LugarUso(models.TextChoices):
        DENTRO_SEDE = 'dentro_sede', 'Dentro de sede'
        FUERA_SEDE = 'fuera_sede', 'Fuera de sede'

    solicitante = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name='solicitudes',
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Solicitud'
        verbose_name_plural = 'Solicitudes'
        ordering = ['-created_at']

    def __str__(self):
        return f'Solicitud #{self.pk} — {self.get_estado_display()}'


class SolicitudItem(models.Model):
    """Detalle de la solicitud: permite varios equipos/insumos por solicitud (kits).
    Hallazgo entrevista #11."""

    solicitud = models.ForeignKey(
        Solicitud, on_delete=models.CASCADE, related_name='items',
    )
    equipo = models.ForeignKey(
        Equipo, on_delete=models.CASCADE, blank=True, null=True,
    )
    insumo = models.ForeignKey(
        Insumo, on_delete=models.CASCADE, blank=True, null=True,
    )
    cantidad = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = 'Ítem de solicitud'
        verbose_name_plural = 'Ítems de solicitud'

    def __str__(self):
        nombre = self.equipo.nombre if self.equipo else self.insumo.nombre
        return f'{nombre} x{self.cantidad}'

class Movimiento(models.Model):
    """Registro de entrega / devolucion para trazabilidad completa."""

    class TipoMovimiento(models.TextChoices):
        ENTREGA = 'entrega', 'Entrega'
        DEVOLUCION = 'devolucion', 'Devolución'

    solicitud = models.ForeignKey(
        Solicitud, on_delete=models.CASCADE, related_name='movimientos',
    )
    tipo = models.CharField(max_length=10, choices=TipoMovimiento.choices)
    fecha = models.DateTimeField(auto_now_add=True)
    responsable = models.ForeignKey(
        Usuario, on_delete=models.CASCADE, related_name='movimientos_responsable',
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
    """Registro de bloqueo por devolucion atrasada."""

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
    """Registro de mantenimiento con la regla del 70%."""

    class Decision(models.TextChoices):
        REPARAR = 'reparar', 'Reparar'
        DAR_BAJA = 'dar_baja', 'Dar de baja'
        PENDIENTE = 'pendiente', 'Pendiente'

    equipo = models.ForeignKey(
        Equipo, on_delete=models.CASCADE, related_name='mantenimientos',
    )
    falla_descrita = models.TextField(blank=True, null=True)
    costo_cotizado = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True,
    )
    porcentaje_costo = models.DecimalField(
        max_digits=5, decimal_places=4, blank=True, null=True,
        help_text='costo_cotizado / valor_adquisicion',
    )
    decision = models.CharField(
        max_length=10, choices=Decision.choices, default=Decision.PENDIENTE,
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
    """Registro de migraciones CSV realizadas."""

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
