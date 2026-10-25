from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario, Equipo, Insumo, Solicitud, SolicitudItem, Movimiento, Bloqueo, Mantenimiento, Migracion, HistorialEquipo, EventoSeguridad
from . import auditoria


@admin.register(Usuario)
class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'rol', 'is_active', 'is_staff')
    list_filter = ('rol', 'is_active', 'is_staff')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email',)
    fieldsets = UserAdmin.fieldsets + (
        ('Datos INACAP', {'fields': ('rol', 'seccion', 'bloqueado_hasta')}),
    )


@admin.register(Equipo)
class EquipoAdmin(admin.ModelAdmin):
    list_display = ('codigo_inventario', 'nombre', 'modelo', 'estado', 'ubicacion')
    list_filter = ('estado',)
    search_fields = ('codigo_inventario', 'nombre', 'modelo')

    def save_model(self, request, obj, form, change):
        antes = auditoria.foto(Equipo.objects.get(pk=obj.pk)) if change else None
        super().save_model(request, obj, form, change)
        accion = HistorialEquipo.Accion.EDITADO if change else HistorialEquipo.Accion.CREADO
        auditoria.registrar(obj, request.user, accion, antes, 'Admin de Django')

    def delete_model(self, request, obj):
        auditoria.registrar(obj, request.user, HistorialEquipo.Accion.ELIMINADO, detalle='Admin de Django')
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            auditoria.registrar(obj, request.user, HistorialEquipo.Accion.ELIMINADO, detalle='Admin de Django')
        super().delete_queryset(request, queryset)


@admin.register(HistorialEquipo)
class HistorialEquipoAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'codigo_inventario', 'accion', 'usuario', 'detalle')
    list_filter = ('accion',)
    search_fields = ('codigo_inventario', 'detalle')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Insumo)
class InsumoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'categoria', 'tipo', 'cantidad_disponible', 'cantidad_total', 'bajo_stock')
    list_filter = ('tipo', 'categoria')
    search_fields = ('nombre',)
    
    def bajo_stock(self, obj):
        return obj.bajo_stock
    bajo_stock.boolean = True


class SolicitudItemInline(admin.TabularInline):
    model = SolicitudItem
    extra = 0


@admin.register(Solicitud)
class SolicitudAdmin(admin.ModelAdmin):
    list_display = ('id', 'solicitante', 'estado', 'horario_inicio', 'horario_fin')
    list_filter = ('estado', 'lugar_uso')
    search_fields = ('solicitante__email', 'solicitante__first_name')
    inlines = [SolicitudItemInline]


@admin.register(Movimiento)
class MovimientoAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'tipo', 'solicitud', 'responsable')
    list_filter = ('tipo',)
    search_fields = ('responsable__email', 'responsable__first_name')


@admin.register(Bloqueo)
class BloqueoAdmin(admin.ModelAdmin):
    list_display = ('usuario', 'fecha_inicio', 'fecha_fin', 'motivo')
    search_fields = ('usuario__email', 'usuario__first_name')


@admin.register(Mantenimiento)
class MantenimientoAdmin(admin.ModelAdmin):
    list_display = ('equipo', 'fecha_diagnostico', 'decision', 'porcentaje_costo')
    list_filter = ('decision',)


@admin.register(Migracion)
class MigracionAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'archivo_origen', 'filas_importadas', 'filas_con_error')


@admin.register(EventoSeguridad)
class EventoSeguridadAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'tipo', 'identificador', 'ip', 'ruta', 'detalle')
    list_filter = ('tipo',)
    search_fields = ('identificador', 'ip', 'ruta')
    date_hierarchy = 'fecha'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
