from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from . import views

urlpatterns = [

    path('login/', LoginView.as_view(template_name='inventario/login.html'), name='login'),
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
    path('cuenta/contrasena/', views.CambiarContrasenaView.as_view(), name='cambiar_contrasena'),

    path('', views.dashboard_view, name='dashboard'),
    path('inventario/', views.inventario_view, name='inventario'),
    path('inventario/equipo/<int:id>/', views.ficha_equipo, name='ficha_equipo'),
    path('inventario/equipo/<int:id>/eliminar/', views.eliminar_equipo, name='eliminar_equipo'),
    path('inventario/equipo/<int:id>/editar/', views.editar_equipo, name='editar_equipo'),
    path('inventario/equipo/<int:id>/qr/', views.qr_equipo, name='qr_equipo'),
    path('inventario/equipo/<int:id>/historial/', views.historial_equipo, name='historial_equipo'),
    path('inventario/insumo/<int:id>/eliminar/', views.eliminar_insumo, name='eliminar_insumo'),
    path('inventario/insumo/<int:id>/editar/', views.editar_insumo, name='editar_insumo'),
    path('inventario/exportar/', views.exportar_inventario, name='exportar_inventario'),
    path('inventario/importar/', views.importar_inventario_view, name='importar_inventario'),
    path('inventario/importar/plantilla/', views.plantilla_importacion, name='plantilla_importacion'),
    path('solicitudes/', views.solicitudes_view, name='solicitudes'),
    path('mantenimiento/', views.mantenimiento_view, name='mantenimiento'),
    path('reportes/', views.reportes_view, name='reportes'),
    path('busqueda/', views.busqueda_view, name='busqueda'),
    path('panel-admin/', views.admin_panel_view, name='admin_panel'),
    path('tareas/', views.tareas_view, name='tareas'),
]
