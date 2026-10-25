from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .. import servicios
from ..models import Equipo, Movimiento, Usuario
from ..seguridad import registrar_cambio_cuenta

ACCIONES_SOBRE_CUENTAS = ('cambiar_rol', 'toggle_activo', 'desbloquear', 'reset_password')


def _errores_password(password, usuario):
    try:
        validate_password(password, user=usuario)
    except ValidationError as e:
        return ' '.join(e.messages)
    return None


def _username_libre(email):
    base = username = email.split('@')[0]
    contador = 1
    while Usuario.objects.filter(username=username).exists():
        username = f'{base}_{contador}'
        contador += 1
    return username


def _verificar_permisos(request, accion):
    if request.user.is_superuser:
        return
    if accion in ACCIONES_SOBRE_CUENTAS:
        objetivo = get_object_or_404(Usuario, id=request.POST.get('user_id'))
        if objetivo != request.user and (objetivo.is_staff or objetivo.is_superuser):
            raise ValueError('Solo un superusuario puede modificar la cuenta de otro administrador.')
        if objetivo == request.user and accion in ('cambiar_rol', 'desbloquear'):
            raise ValueError('No puedes cambiar tu propio rol ni quitarte una sanción.')
    rol_pedido = request.POST.get('nuevo_rol') if accion == 'cambiar_rol' else request.POST.get('rol')
    if accion in ('cambiar_rol', 'crear_usuario') and rol_pedido in Usuario.ROLES_APROBADORES:
        raise ValueError('Solo un superusuario puede asignar roles con permisos de aprobación.')


def _crear_usuario(request):
    email = request.POST.get('email', '').strip().lower()
    nombre = request.POST.get('first_name', '').strip()
    apellido = request.POST.get('last_name', '').strip()
    rol = request.POST.get('rol')
    password = request.POST.get('password', '')
    es_staff = request.POST.get('is_staff') == 'on' and request.user.is_superuser

    dominio = settings.DOMINIO_INSTITUCIONAL
    if not email.endswith(f'@{dominio}') and not email.endswith('@inacapmail.cl'):
        raise ValueError(f'El correo debe pertenecer al dominio institucional (@{dominio}).')
    if rol not in Usuario.Rol.values:
        raise ValueError('Rol no válido.')
    if Usuario.objects.filter(email=email).exists():
        raise ValueError(f'Ya existe un usuario registrado con el correo {email}.')
    if error := _errores_password(password, Usuario(email=email, first_name=nombre, last_name=apellido)):
        raise ValueError(error)

    usuario = Usuario.objects.create_user(
        username=_username_libre(email), email=email, first_name=nombre, last_name=apellido,
        rol=rol, seccion=request.POST.get('seccion', '').strip(), password=password, is_staff=es_staff,
    )
    registrar_cambio_cuenta(request, usuario, f'cuenta creada con rol {usuario.get_rol_display()}' + (' (staff)' if es_staff else ''))
    return f'Usuario {usuario.email} ({usuario.get_rol_display()}) creado exitosamente.'


def _cambiar_rol(request, usuario):
    nuevo_rol = request.POST.get('nuevo_rol')
    if nuevo_rol not in Usuario.Rol.values:
        raise ValueError('Rol no válido.')
    rol_anterior = usuario.get_rol_display()
    usuario.rol = nuevo_rol
    usuario.save(update_fields=['rol'])
    registrar_cambio_cuenta(request, usuario, f'rol {rol_anterior} → {usuario.get_rol_display()}')
    return f'Rol de {usuario.email} actualizado a {usuario.get_rol_display()}.'


def _alternar_activo(request, usuario):
    if usuario == request.user:
        raise ValueError('No puedes desactivar tu propia cuenta en uso.')
    usuario.is_active = not usuario.is_active
    usuario.save(update_fields=['is_active'])
    estado = 'activada' if usuario.is_active else 'desactivada'
    registrar_cambio_cuenta(request, usuario, f'cuenta {estado}')
    return f'Cuenta {usuario.email} {estado}.'


def _desbloquear(request, usuario):
    usuario.bloqueado_hasta = None
    usuario.save(update_fields=['bloqueado_hasta'])
    registrar_cambio_cuenta(request, usuario, 'sanción removida')
    return f'Sanción removida: {usuario.email} ahora está desbloqueado.'


def _restablecer_password(request, usuario):
    nueva = request.POST.get('nueva_password', '')
    if error := _errores_password(nueva, usuario):
        raise ValueError(error)
    usuario.set_password(nueva)
    usuario.save(update_fields=['password'])
    registrar_cambio_cuenta(request, usuario, 'contraseña restablecida')
    return f'Contraseña de {usuario.email} restablecida correctamente.'


def _cambiar_estado_equipo(request):
    equipo = get_object_or_404(Equipo, id=request.POST.get('equipo_id'))
    anterior = equipo.get_estado_display()
    servicios.cambiar_estado_manual(equipo, request.user, request.POST.get('nuevo_estado'), 'Panel de administración')
    return (f'Estado del equipo "{equipo.nombre}" ({equipo.codigo_inventario}) '
            f'actualizado exitosamente de {anterior} a {equipo.get_estado_display()}.')


ACCIONES_CUENTA = {
    'cambiar_rol': _cambiar_rol,
    'toggle_activo': _alternar_activo,
    'desbloquear': _desbloquear,
    'reset_password': _restablecer_password,
}


def _procesar(request):
    accion = request.POST.get('accion')
    for campo in ('user_id', 'equipo_id'):
        if campo in request.POST and not request.POST[campo].isdigit():
            raise ValueError('Identificador no válido.')
    _verificar_permisos(request, accion)
    if accion == 'crear_usuario':
        return _crear_usuario(request)
    if accion == 'cambiar_estado_equipo':
        return _cambiar_estado_equipo(request)
    if accion in ACCIONES_CUENTA:
        return ACCIONES_CUENTA[accion](request, get_object_or_404(Usuario, id=request.POST.get('user_id')))
    return None


def _metricas():
    return {
        **Usuario.objects.aggregate(
            total_usuarios=Count('id'),
            estudiantes=Count('id', filter=Q(rol=Usuario.Rol.ESTUDIANTE)),
            docentes=Count('id', filter=Q(rol=Usuario.Rol.DOCENTE)),
            directores=Count('id', filter=Q(rol=Usuario.Rol.DIRECTOR_CARRERA)),
            encargados=Count('id', filter=Q(rol=Usuario.Rol.ENCARGADO_LABORATORIO)),
            control_calidad=Count('id', filter=Q(rol=Usuario.Rol.CONTROL_CALIDAD)),
            bloqueados=Count('id', filter=Q(bloqueado_hasta__gt=timezone.now())),
            staff=Count('id', filter=Q(is_staff=True)),
        ),
        **Equipo.objects.aggregate(
            equipos_total=Count('id'),
            equipos_disponibles=Count('id', filter=Q(estado=Equipo.Estado.DISPONIBLE)),
            equipos_mantenimiento=Count('id', filter=Q(estado=Equipo.Estado.EN_MANTENIMIENTO)),
            equipos_prestados=Count('id', filter=Q(estado=Equipo.Estado.PRESTADO)),
            equipos_baja=Count('id', filter=Q(estado=Equipo.Estado.FUERA_SERVICIO)),
        ),
    }


@login_required
def admin_panel_view(request):
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, 'Acceso denegado: este panel es exclusivo para administradores del sistema.')
        return redirect('dashboard')

    if request.method == 'POST':
        try:
            mensaje = _procesar(request)
        except ValueError as e:
            messages.error(request, str(e))
        else:
            if mensaje:
                messages.success(request, mensaje)
        return redirect('admin_panel')

    filtro_rol = request.GET.get('rol', '')
    busqueda = request.GET.get('q', '').strip()
    busqueda_equipo = request.GET.get('q_equipo', '').strip()
    filtro_estado_equipo = request.GET.get('estado_equipo', '').strip()

    usuarios = Usuario.objects.order_by('-date_joined')
    if filtro_rol:
        usuarios = usuarios.filter(rol=filtro_rol)
    if busqueda:
        usuarios = usuarios.filter(Q(email__icontains=busqueda) | Q(first_name__icontains=busqueda) | Q(last_name__icontains=busqueda))

    equipos = Equipo.objects.order_by('nombre')
    if busqueda_equipo:
        equipos = equipos.filter(
            Q(codigo_inventario__icontains=busqueda_equipo) | Q(nombre__icontains=busqueda_equipo) | Q(modelo__icontains=busqueda_equipo)
        )
    if filtro_estado_equipo:
        equipos = equipos.filter(estado=filtro_estado_equipo)

    return render(request, 'inventario/admin_panel.html', {
        'usuarios': Paginator(usuarios, 25).get_page(request.GET.get('page_usuarios')),
        'equipos_admin': Paginator(equipos, 25).get_page(request.GET.get('page_equipos')),
        'metricas': _metricas(),
        'roles_choices': Usuario.Rol.choices,
        'estados_equipos_choices': Equipo.Estado.choices,
        'filtro_rol': filtro_rol,
        'busqueda': busqueda,
        'busqueda_equipo': busqueda_equipo,
        'filtro_estado_equipo': filtro_estado_equipo,
        'ultimos_movimientos': Movimiento.objects.select_related('solicitud', 'responsable').order_by('-fecha')[:10],
    })
