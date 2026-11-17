from .busqueda import busqueda_view, calificar_busqueda, generar_respuesta
from .cuenta import CambiarContrasenaView
from .dashboard import dashboard_view
from .inventario import (
    editar_equipo,
    editar_insumo,
    eliminar_equipo,
    eliminar_insumo,
    exportar_inventario,
    ficha_equipo,
    historial_equipo,
    importar_inventario_view,
    inventario_view,
    plantilla_importacion,
    qr_equipo,
)
from .mantenimiento import mantenimiento_view
from .panel import admin_panel_view
from .reportes import evaluar_busqueda, exportar_reportes, reportes_view
from .solicitudes import solicitudes_view
from .tareas import tareas_view

__all__ = [
    'CambiarContrasenaView', 'admin_panel_view', 'busqueda_view', 'calificar_busqueda', 'dashboard_view',
    'editar_equipo', 'editar_insumo', 'eliminar_equipo', 'eliminar_insumo', 'evaluar_busqueda',
    'exportar_inventario', 'exportar_reportes', 'ficha_equipo', 'generar_respuesta', 'historial_equipo',
    'importar_inventario_view', 'inventario_view', 'mantenimiento_view', 'plantilla_importacion', 'qr_equipo',
    'reportes_view', 'solicitudes_view', 'tareas_view',
]
