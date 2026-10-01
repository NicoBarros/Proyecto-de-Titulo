from django.urls import path
from django.contrib.auth.views import LoginView, LogoutView
from . import views

urlpatterns = [
    # Auth
    path('login/', LoginView.as_view(template_name='inventario/login.html'), name='login'),
    path('logout/', LogoutView.as_view(next_page='login'), name='logout'),
    
    # Dashboard y vistas
    path('', views.dashboard_view, name='dashboard'),
    path('inventario/', views.inventario_view, name='inventario'),
    path('inventario/equipo/<int:id>/eliminar/', views.eliminar_equipo, name='eliminar_equipo'),
    path('inventario/equipo/<int:id>/editar/', views.editar_equipo, name='editar_equipo'),
    path('inventario/insumo/<int:id>/eliminar/', views.eliminar_insumo, name='eliminar_insumo'),
    path('inventario/insumo/<int:id>/editar/', views.editar_insumo, name='editar_insumo'),
    path('inventario/exportar/', views.exportar_inventario, name='exportar_inventario'),
    path('solicitudes/', views.solicitudes_view, name='solicitudes'),
    path('mantenimiento/', views.mantenimiento_view, name='mantenimiento'),
    path('reportes/', views.reportes_view, name='reportes'),
    path('busqueda/', views.busqueda_view, name='busqueda'),
    path('migracion/', views.migracion_view, name='migracion'),
]
