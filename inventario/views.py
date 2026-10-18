from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib import messages
from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Count, Q
from django.utils import timezone
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.db import transaction
from datetime import timedelta
import json
import csv
import io

from .models import (
    Usuario, Equipo, Insumo, Solicitud, SolicitudItem, Movimiento,
    Bloqueo, Mantenimiento, Migracion
)
from .forms import EquipoForm, InsumoForm, MantenimientoForm
from .decorators import role_required


@login_required
def dashboard_view(request):
    totales = {
        'total_equipos': Equipo.objects.count(),
        'equipos_disponibles': Equipo.objects.filter(estado=Equipo.Estado.DISPONIBLE).count(),
        'equipos_prestados': Equipo.objects.filter(estado=Equipo.Estado.PRESTADO).count(),
        'equipos_mantenimiento': Equipo.objects.filter(estado=Equipo.Estado.EN_MANTENIMIENTO).count(),
        'solicitudes_pendientes': Solicitud.objects.filter(estado=Solicitud.EstadoSolicitud.PENDIENTE).count(),
        'solicitudes_atrasadas': Solicitud.objects.filter(estado=Solicitud.EstadoSolicitud.ATRASADA).count(),
        'insumos_bajo_stock': len([i for i in Insumo.objects.all() if i.bajo_stock]),
    }
    return render(request, 'inventario/dashboard.html', {'totales': totales})


@login_required
def inventario_view(request):
    puede_escribir = request.user.rol in Usuario.ROLES_ESCRITURA_INVENTARIO
    tab = request.GET.get('tab', 'equipos')
    
    context = {'puede_escribir': puede_escribir, 'tab': tab}
    
    if tab == 'equipos':
        q = request.GET.get('q', '').strip()
        filtro_estado = request.GET.get('estado', '').strip()
        filtro_ubicacion = request.GET.get('ubicacion', '').strip()
        orden = request.GET.get('orden', 'nombre')

        qs = Equipo.objects.all()

        if q:
            qs = qs.filter(
                Q(codigo_inventario__icontains=q) |
                Q(nombre__icontains=q) |
                Q(modelo__icontains=q) |
                Q(especificaciones__icontains=q) |
                Q(ubicacion__icontains=q)
            )

        if filtro_estado:
            qs = qs.filter(estado=filtro_estado)

        if filtro_ubicacion:
            qs = qs.filter(ubicacion__icontains=filtro_ubicacion)

        orden_map = {
            'nombre': 'nombre',
            '-nombre': '-nombre',
            'codigo': 'codigo_inventario',
            '-codigo': '-codigo_inventario',
            'estado': 'estado',
            '-estado': '-estado',
            '-valor': '-valor_adquisicion',
            'valor': 'valor_adquisicion',
            '-recientes': '-created_at',
        }
        qs = qs.order_by(orden_map.get(orden, 'nombre'))

        ubicaciones = Equipo.objects.exclude(ubicacion__isnull=True).exclude(ubicacion='').values_list('ubicacion', flat=True).distinct()

        context['equipos'] = qs
        context['total_equipos_filtrados'] = qs.count()
        context['total_equipos_general'] = Equipo.objects.count()
        context['q'] = q
        context['filtro_estado'] = filtro_estado
        context['filtro_ubicacion'] = filtro_ubicacion
        context['orden'] = orden
        context['estados_choices'] = Equipo.Estado.choices
        context['ubicaciones'] = sorted(list(set(ubicaciones)))

        if puede_escribir and request.method == 'POST' and 'codigo_inventario' in request.POST:
            form = EquipoForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, 'Equipo agregado exitosamente.')
                return redirect('/inventario/?tab=equipos')
            else:
                messages.error(request, 'Error al agregar equipo.')
    else:
        q_insumo = request.GET.get('q_insumo', '').strip()
        filtro_categoria = request.GET.get('categoria', '').strip()
        filtro_tipo = request.GET.get('tipo', '').strip()
        filtro_stock = request.GET.get('stock', '').strip()

        qs = Insumo.objects.all()

        if q_insumo:
            qs = qs.filter(
                Q(nombre__icontains=q_insumo) |
                Q(categoria__icontains=q_insumo)
            )

        if filtro_categoria:
            qs = qs.filter(categoria__icontains=filtro_categoria)

        if filtro_tipo:
            qs = qs.filter(tipo=filtro_tipo)

        if filtro_stock == 'bajo':
            qs = [i for i in qs if i.bajo_stock]
        elif filtro_stock == 'agotado':
            qs = qs.filter(cantidad_disponible=0)
        elif filtro_stock == 'disponible':
            qs = qs.filter(cantidad_disponible__gt=0)

        categorias = Insumo.objects.exclude(categoria__isnull=True).exclude(categoria='').values_list('categoria', flat=True).distinct()

        context['insumos'] = qs
        context['total_insumos_general'] = Insumo.objects.count()
        context['q_insumo'] = q_insumo
        context['filtro_categoria'] = filtro_categoria
        context['filtro_tipo'] = filtro_tipo
        context['filtro_stock'] = filtro_stock
        context['tipos_choices'] = Insumo.Tipo.choices
        context['categorias'] = sorted(list(set(categorias)))

        if puede_escribir and request.method == 'POST' and 'cantidad_total' in request.POST:
            form = InsumoForm(request.POST)
            if form.is_valid():
                insumo = form.save(commit=False)
                insumo.cantidad_disponible = insumo.cantidad_total
                insumo.save()
                messages.success(request, 'Insumo agregado exitosamente.')
                return redirect('/inventario/?tab=insumos')
            else:
                messages.error(request, 'Error al agregar insumo.')
                
    return render(request, 'inventario/inventario.html', context)


@login_required
@role_required(Usuario.Rol.ENCARGADO_LABORATORIO, Usuario.Rol.CONTROL_CALIDAD)
def eliminar_equipo(request, id):
    equipo = get_object_or_404(Equipo, id=id)
    if request.method == 'POST':
        if equipo.estado not in [Equipo.Estado.DISPONIBLE, Equipo.Estado.FUERA_SERVICIO]:
            messages.error(request, 'No puedes eliminar un equipo que está prestado o en mantenimiento.')
        else:
            equipo.delete()
            messages.success(request, 'Equipo eliminado exitosamente.')
    return redirect('/inventario/?tab=equipos')


@login_required
@role_required(Usuario.Rol.ENCARGADO_LABORATORIO, Usuario.Rol.CONTROL_CALIDAD)
def editar_equipo(request, id):
    equipo = get_object_or_404(Equipo, id=id)
    if request.method == 'POST':
        form = EquipoForm(request.POST, instance=equipo)
        if form.is_valid():
            equipo = form.save(commit=False)
            equipo.version += 1
            equipo.save()
            messages.success(request, 'Equipo actualizado exitosamente.')
            return redirect('/inventario/?tab=equipos')
    else:
        form = EquipoForm(instance=equipo)
    return render(request, 'inventario/editar_equipo.html', {'form': form, 'equipo': equipo})


@login_required
@role_required(Usuario.Rol.ENCARGADO_LABORATORIO, Usuario.Rol.CONTROL_CALIDAD)
def eliminar_insumo(request, id):
    insumo = get_object_or_404(Insumo, id=id)
    if request.method == 'POST':
        insumo.delete()
        messages.success(request, 'Insumo eliminado exitosamente.')
    return redirect('/inventario/?tab=insumos')


@login_required
@role_required(Usuario.Rol.ENCARGADO_LABORATORIO, Usuario.Rol.CONTROL_CALIDAD)
def editar_insumo(request, id):
    insumo = get_object_or_404(Insumo, id=id)
    if request.method == 'POST':
        form = InsumoForm(request.POST, instance=insumo)
        if form.is_valid():
            insumo_editado = form.save(commit=False)
            insumo_editado.version += 1
            insumo_editado.save()
            messages.success(request, 'Insumo actualizado exitosamente.')
            return redirect('/inventario/?tab=insumos')
    else:
        form = InsumoForm(instance=insumo)
    return render(request, 'inventario/editar_insumo.html', {'form': form, 'insumo': insumo})

@login_required
def solicitudes_view(request):
    puede_aprobar = (
        request.user.rol in Usuario.ROLES_APROBADORES or
        request.user.is_staff or
        request.user.is_superuser
    )
    if request.method == 'POST' and 'item[]' in request.POST:
        items = request.POST.getlist('item[]')
        cantidades = request.POST.getlist('cantidad[]')
        
        try:
            with transaction.atomic():
                solicitud = Solicitud.objects.create(
                    solicitante=request.user,
                    lugar_uso=request.POST.get('lugar_uso'),
                    justificacion=request.POST.get('justificacion'),
                    horario_inicio=request.POST.get('horario_inicio'),
                    horario_fin=request.POST.get('horario_fin'),
                )
                
                for i in range(len(items)):
                    tipo, item_id = items[i].split(':')
                    cantidad = int(cantidades[i]) if i < len(cantidades) else 1
                    
                    if tipo == 'equipo':
                        equipo = get_object_or_404(Equipo, id=item_id)
                        if equipo.estado != Equipo.Estado.DISPONIBLE:
                            raise ValueError(f'El equipo {equipo.nombre} no se encuentra disponible actualmente.')
                        SolicitudItem.objects.create(solicitud=solicitud, equipo_id=item_id, cantidad=1)
                    else:
                        insumo = get_object_or_404(Insumo, id=item_id)
                        if insumo.cantidad_disponible < cantidad:
                            raise ValueError(f'No hay stock suficiente para {insumo.nombre}. Disponible: {insumo.cantidad_disponible}.')
                        SolicitudItem.objects.create(solicitud=solicitud, insumo_id=item_id, cantidad=cantidad)
                        
                messages.success(request, 'Solicitud (Kit) creada correctamente.')
        except ValueError as e:
            messages.error(request, str(e))
            
        return redirect('solicitudes')

    if request.method == 'POST' and 'accion' in request.POST:
        if not puede_aprobar:
            messages.error(request, 'No tienes permiso para aprobar solicitudes.')
            return redirect('solicitudes')
            
        solicitud_id = request.POST.get('solicitud_id')
        accion = request.POST.get('accion')
        solicitud = get_object_or_404(Solicitud, id=solicitud_id)
        
        try:
            if accion == 'aprobar':
                for item in solicitud.items.all():
                    if item.equipo:
                        choque = SolicitudItem.objects.filter(
                            equipo=item.equipo,
                            solicitud__estado__in=[Solicitud.EstadoSolicitud.APROBADA, Solicitud.EstadoSolicitud.ENTREGADA]
                        ).exclude(solicitud=solicitud).filter(
                            Q(solicitud__horario_inicio__lt=solicitud.horario_fin) & 
                            Q(solicitud__horario_fin__gt=solicitud.horario_inicio)
                        ).exists()
                        if choque:
                            raise ValueError(f'El equipo {item.equipo} ya esta reservado en ese horario.')
                            
                solicitud.estado = Solicitud.EstadoSolicitud.APROBADA
                solicitud.aprobado_por = request.user
                solicitud.fecha_aprobacion = timezone.now()
                solicitud.save()
                
            elif accion == 'entregar':
                for item in solicitud.items.all():
                    if item.equipo:
                        item.equipo.estado = Equipo.Estado.PRESTADO
                        item.equipo.version += 1
                        item.equipo.save()
                    elif item.insumo:
                        if item.insumo.cantidad_disponible < item.cantidad:
                            raise ValueError(f'Stock insuficiente para {item.insumo.nombre}.')
                        item.insumo.cantidad_disponible -= item.cantidad
                        item.insumo.version += 1
                        item.insumo.save()
                        
                solicitud.estado = Solicitud.EstadoSolicitud.ENTREGADA
                solicitud.save()
                Movimiento.objects.create(solicitud=solicitud, tipo=Movimiento.TipoMovimiento.ENTREGA, responsable=request.user)
                
            elif accion == 'devolver':
                estado_equipo = request.POST.get('estado_equipo', 'bueno')
                atrasada = timezone.now() > solicitud.horario_fin
                
                for item in solicitud.items.all():
                    if item.equipo:
                        nuevo_estado = Equipo.Estado.EN_MANTENIMIENTO if estado_equipo in ['dañado', 'inservible'] else Equipo.Estado.DISPONIBLE
                        item.equipo.estado = nuevo_estado
                        item.equipo.version += 1
                        item.equipo.save()
                    elif item.insumo and item.insumo.tipo == Insumo.Tipo.RENOVABLE:
                        item.insumo.cantidad_disponible += item.cantidad
                        item.insumo.version += 1
                        item.insumo.save()
                
                solicitud.estado = Solicitud.EstadoSolicitud.ATRASADA if atrasada else Solicitud.EstadoSolicitud.DEVUELTA
                solicitud.save()
                Movimiento.objects.create(
                    solicitud=solicitud, 
                    tipo=Movimiento.TipoMovimiento.DEVOLUCION, 
                    responsable=request.user,
                    estado_equipo=estado_equipo,
                )
                
                if atrasada:
                    usuario = solicitud.en_representacion_de or solicitud.solicitante
                    hasta = timezone.now() + timedelta(days=7)
                    usuario.bloqueado_hasta = hasta
                    usuario.save()
                    Bloqueo.objects.create(
                        usuario=usuario, seccion=usuario.seccion, solicitud=solicitud,
                        fecha_fin=hasta, motivo='Devolucion atrasada'
                    )
            
            elif accion == 'rechazar':
                solicitud.estado = Solicitud.EstadoSolicitud.RECHAZADA
                solicitud.save()
                
            messages.success(request, f'Solicitud {accion} correctamente.')
        except ValueError as e:
            messages.error(request, str(e))
            
        return redirect('solicitudes')

    solicitudes = Solicitud.objects.all().prefetch_related('items', 'items__equipo', 'items__insumo')
    equipos = Equipo.objects.filter(estado=Equipo.Estado.DISPONIBLE)
    insumos = Insumo.objects.all()
    
    return render(request, 'inventario/solicitudes.html', {
        'solicitudes': solicitudes, 'equipos': equipos, 'insumos': insumos, 'puede_aprobar': puede_aprobar
    })


@login_required
@role_required(Usuario.Rol.ENCARGADO_LABORATORIO, Usuario.Rol.CONTROL_CALIDAD, Usuario.Rol.DIRECTOR_CARRERA)
def mantenimiento_view(request):
    """RF-10: Mantenimiento y regla del 70% con finalización de reparación."""
    if request.method == 'POST':
        if 'mant_id' in request.POST or 'decision' in request.POST or 'accion_mant' in request.POST:
            mant_id = request.POST.get('mant_id')
            accion = request.POST.get('accion_mant') or request.POST.get('decision')
            mant = get_object_or_404(Mantenimiento, id=mant_id)

            if accion in ['completar_reparacion', 'completado']:
                mant.decision = Mantenimiento.Decision.COMPLETADO
                mant.fecha_resolucion = timezone.now()
                mant.save()

                mant.equipo.estado = Equipo.Estado.DISPONIBLE
                mant.equipo.version += 1
                mant.equipo.save()
                messages.success(
                    request,
                    f'¡Reparación completada! El equipo "{mant.equipo.nombre}" ({mant.equipo.codigo_inventario}) '
                    f'ha salido de reparación y su estado en el inventario se actualizó a DISPONIBLE.'
                )
            elif accion == 'dar_baja':
                mant.decision = Mantenimiento.Decision.DAR_BAJA
                mant.fecha_resolucion = timezone.now()
                mant.save()

                mant.equipo.estado = Equipo.Estado.FUERA_SERVICIO
                mant.equipo.version += 1
                mant.equipo.save()
                messages.warning(request, f'El equipo "{mant.equipo.nombre}" ha sido dado de baja (Fuera de servicio).')
            elif accion == 'reparar':
                mant.decision = Mantenimiento.Decision.REPARAR
                mant.fecha_resolucion = timezone.now()
                mant.save()

                mant.equipo.estado = Equipo.Estado.EN_MANTENIMIENTO
                mant.equipo.version += 1
                mant.equipo.save()
                messages.info(request, f'El equipo "{mant.equipo.nombre}" ha sido confirmado en proceso de reparación.')
        else:
            form = MantenimientoForm(request.POST)
            if form.is_valid():
                equipo = get_object_or_404(Equipo, id=form.cleaned_data['equipo_id'])
                costo = Decimal(form.cleaned_data['costo_cotizado'])

                if equipo.valor_adquisicion:
                    porcentaje = (costo / Decimal(equipo.valor_adquisicion)).quantize(
                        Decimal('0.0001'), rounding=ROUND_HALF_UP
                    )
                else:
                    porcentaje = None

                sugerencia = (
                    Mantenimiento.Decision.DAR_BAJA
                    if porcentaje is not None and porcentaje >= Decimal('0.70')
                    else Mantenimiento.Decision.REPARAR
                )

                Mantenimiento.objects.create(
                    equipo=equipo,
                    falla_descrita=form.cleaned_data['falla_descrita'],
                    costo_cotizado=costo,
                    porcentaje_costo=porcentaje,
                    decision=sugerencia,
                    reportado_por=request.user
                )

                equipo.estado = Equipo.Estado.EN_MANTENIMIENTO
                equipo.version += 1
                equipo.save()

                msg = f"Diagnóstico registrado. Sugerencia del sistema: {sugerencia.upper()} "
                if porcentaje is not None:
                    msg += f"(Costo representa {(porcentaje * 100):.1f}% del valor de adquisición)"
                else:
                    msg += "(Sin valor de adquisición registrado)"
                messages.info(request, msg)

        return redirect('mantenimiento')

    mantenimientos = Mantenimiento.objects.all().select_related('equipo')
    equipos = Equipo.objects.all()
    return render(request, 'inventario/mantenimiento.html', {'mantenimientos': mantenimientos, 'equipos': equipos})


@login_required
def reportes_view(request):
    """RF-13: Reportes (Restringido para Estudiantes y Docentes)."""
    if request.user.rol in [Usuario.Rol.ESTUDIANTE, Usuario.Rol.DOCENTE] and not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, 'Acceso denegado: Los estudiantes y docentes no tienen autorización para ver Reportes y KPIs.')
        return redirect('dashboard')

    top_equipos = Equipo.objects.annotate(veces=Count('solicituditem')).order_by('-veces')[:20]
    vencidos = Solicitud.objects.filter(estado=Solicitud.EstadoSolicitud.ENTREGADA, horario_fin__lt=timezone.now()).select_related('solicitante')
    
    dias_str = request.GET.get('dias', '90')
    dias = int(dias_str) if dias_str.isdigit() else 90
    fecha_limite = timezone.now() - timedelta(days=dias)
    sin_movimiento = Equipo.objects.exclude(
        solicituditem__solicitud__created_at__gte=fecha_limite
    )
    
    return render(request, 'inventario/reportes.html', {
        'top_equipos': top_equipos, 'vencidos': vencidos, 'sin_movimiento': sin_movimiento, 'dias': dias
    })

import json
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.conf import settings
from .models import Equipo 

@login_required
def busqueda_view(request):
    """
    RF-11 / RNF-06: Busqueda por IA.
    Actualizado a Google Gemini con tolerancia a fallos (Error 503).
    """
    if request.method == 'GET':
        return render(request, 'inventario/busqueda.html')
        
    consulta = request.POST.get('consulta')
    disponibles = list(Equipo.objects.filter(estado=Equipo.Estado.DISPONIBLE))
    
    if not consulta:
        return JsonResponse({'error': 'Falta consulta'}, status=400)
        
    resultados = []
    fuente = 'palabras_clave_local'
    
    if getattr(settings, 'GEMINI_API_KEY', None):
        try:
            from google import genai
            from google.genai.errors import APIError
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            
            catalogo = "\n".join([f"- id={e.id}: {e.nombre} ({e.modelo or 's/modelo'}) - {e.especificaciones or ''}" for e in disponibles])
            prompt = f"""Eres un asistente que ayuda a un encargado de laboratorio a encontrar equipos.
Catalogo de equipos disponibles:
{catalogo}

Necesidad del usuario: "{consulta}"

Responde SOLO con un JSON array de los ids de equipo mas relevantes (maximo 5), ordenados del mas al menos relevante. Ejemplo: [3, 1, 7]"""

            try:
                response = client.models.generate_content(
                    model='gemini-3.8-flash',
                    contents=prompt,
                )
            except APIError as e:
                if e.code == 503 or "503" in str(e):
                    response = client.models.generate_content(
                        model='gemini-3.5-flash-lite',
                        contents=prompt,
                    )
                else:
                    raise e  

            text = response.text.replace('```json', '').replace('```', '').strip()
            ids = json.loads(text)
            
            if isinstance(ids, list):
                for item_id in ids:
                    equipo = next((e for e in disponibles if e.id == item_id), None)
                    if equipo:
                        resultados.append({
                            'nombre': equipo.nombre, 
                            'codigo_inventario': equipo.codigo_inventario, 
                            'estado': equipo.get_estado_display()
                        })
                fuente = 'ia_gemini'
                
        except Exception as e:
         
            print(f"Advertencia: Falló la IA de Gemini ({str(e)}). Cayendo a búsqueda local.")
            
   
    if not resultados:
        terminos = consulta.lower().split()
        for e in disponibles:
            texto = f"{e.nombre} {e.modelo or ''} {e.especificaciones or ''}".lower()
            score = sum(1 for t in terminos if t in texto)
            if score > 0:
                e.score = score
                
        disp_con_score = [e for e in disponibles if hasattr(e, 'score')]
        disp_con_score.sort(key=lambda x: x.score, reverse=True)
        
        for e in disp_con_score[:5]:
            resultados.append({
                'nombre': e.nombre, 
                'codigo_inventario': e.codigo_inventario, 
                'estado': e.get_estado_display()
            })
            
    return JsonResponse({'fuente': fuente, 'resultados': resultados})


@login_required
@role_required(Usuario.Rol.ENCARGADO_LABORATORIO, Usuario.Rol.CONTROL_CALIDAD)
def migracion_view(request):
    """RF-14: Migracion de CSV."""
    if request.method == 'GET':
        migraciones = Migracion.objects.all()
        return render(request, 'inventario/migracion.html', {'migraciones': migraciones})
        
    if 'archivo' not in request.FILES:
        messages.error(request, 'Falta el archivo CSV.')
        return redirect('migracion')
        
    archivo = request.FILES['archivo']
    try:
        decoded_file = archivo.read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(decoded_file))
    except Exception as e:
        messages.error(request, f'No se pudo leer el CSV: {e}')
        return redirect('migracion')
        
    importadas = 0
    errores = []
    totales = 0
    
    for idx, fila in enumerate(reader):
        totales += 1
        try:
            tipo = fila.get('tipo', '').lower()
            if tipo == 'equipo':
                if not fila.get('codigo_inventario') or not fila.get('nombre'):
                    raise ValueError('Faltan codigo_inventario/nombre')
                Equipo.objects.update_or_create(
                    codigo_inventario=fila['codigo_inventario'],
                    defaults={
                        'nombre': fila['nombre'],
                        'modelo': fila.get('modelo', ''),
                        'especificaciones': fila.get('especificaciones', ''),
                        'ubicacion': fila.get('ubicacion', ''),
                        'estado': fila.get('estado', Equipo.Estado.DISPONIBLE),
                        'valor_adquisicion': float(fila.get('valor_adquisicion')) if fila.get('valor_adquisicion') else None,
                    }
                )
            elif tipo == 'insumo':
                if not fila.get('nombre'):
                    raise ValueError('Falta nombre')
                cant = int(fila.get('cantidad', 0))
                Insumo.objects.create(
                    nombre=fila['nombre'],
                    categoria=fila.get('categoria', ''),
                    tipo=fila.get('tipo_insumo', Insumo.Tipo.PERECIBLE),
                    cantidad_total=cant,
                    cantidad_disponible=cant
                )
            else:
                raise ValueError(f'Columna "tipo" debe ser equipo o insumo (fila {idx+2})')
            importadas += 1
        except Exception as e:
            errores.append(f"Fila {idx+2}: {e}")
            
    Migracion.objects.create(
        archivo_origen=archivo.name,
        filas_totales=totales,
        filas_importadas=importadas,
        filas_con_error=len(errores),
        detalle_errores=json.dumps(errores),
        ejecutado_por=request.user
    )
    
    if errores:
        messages.warning(request, f'Importadas {importadas}/{totales}. Errores: {len(errores)}. Revisa el historial.')
    else:
        messages.success(request, f'Importación completa: {importadas} registros.')
        
    return redirect('migracion')


@login_required
@role_required(Usuario.Rol.ENCARGADO_LABORATORIO, Usuario.Rol.CONTROL_CALIDAD)
def exportar_inventario(request):
    """Genera y descarga un CSV del inventario (Equipos e Insumos) automáticamente."""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="inventario_leica_{timezone.now().strftime("%Y%m%d")}.csv"'

    writer = csv.writer(response)
    writer.writerow(['tipo', 'codigo_inventario', 'nombre', 'modelo', 'especificaciones', 'ubicacion', 'estado', 'valor_adquisicion', 'categoria', 'tipo_insumo', 'cantidad'])

    equipos = Equipo.objects.all()
    for e in equipos:
        writer.writerow(['equipo', e.codigo_inventario, e.nombre, e.modelo or '', e.especificaciones or '', e.ubicacion or '', e.estado, e.valor_adquisicion or '', '', '', ''])

    insumos = Insumo.objects.all()
    for i in insumos:
        writer.writerow(['insumo', '', i.nombre, '', '', '', '', '', i.categoria or '', i.tipo, i.cantidad_total])

    return response


@login_required
def admin_panel_view(request):
    """Panel de Administración Integrado institucional (no el admin genérico de Django)."""
    if not (request.user.is_staff or request.user.is_superuser):
        messages.error(request, 'Acceso denegado: este panel es exclusivo para administradores del sistema.')
        return redirect('dashboard')

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'crear_usuario':
            email = request.POST.get('email', '').strip().lower()
            nombre = request.POST.get('first_name', '').strip()
            apellido = request.POST.get('last_name', '').strip()
            rol = request.POST.get('rol')
            seccion = request.POST.get('seccion', '').strip()
            password = request.POST.get('password', '')
            es_staff = request.POST.get('is_staff') == 'on'

            dominio = getattr(settings, 'DOMINIO_INSTITUCIONAL', 'inacapmail.cl')
            if not email.endswith(f"@{dominio}") and not email.endswith('@inacapmail.cl'):
                messages.error(request, f'El correo debe pertenecer al dominio institucional (@{dominio}).')
            elif Usuario.objects.filter(email=email).exists():
                messages.error(request, f'Ya existe un usuario registrado con el correo {email}.')
            elif len(password) < 6:
                messages.error(request, 'La contraseña debe tener al menos 6 caracteres.')
            else:
                username = email.split('@')[0]
                base_username = username
                counter = 1
                while Usuario.objects.filter(username=username).exists():
                    username = f"{base_username}_{counter}"
                    counter += 1

                user = Usuario.objects.create_user(
                    username=username,
                    email=email,
                    first_name=nombre,
                    last_name=apellido,
                    rol=rol,
                    seccion=seccion,
                    password=password,
                    is_staff=es_staff,
                )
                messages.success(request, f'Usuario {user.email} ({user.get_rol_display()}) creado exitosamente.')

        elif accion == 'cambiar_rol':
            user_id = request.POST.get('user_id')
            nuevo_rol = request.POST.get('nuevo_rol')
            user_obj = get_object_or_404(Usuario, id=user_id)
            user_obj.rol = nuevo_rol
            user_obj.save()
            messages.success(request, f'Rol de {user_obj.email} actualizado a {user_obj.get_rol_display()}.')

        elif accion == 'toggle_activo':
            user_id = request.POST.get('user_id')
            user_obj = get_object_or_404(Usuario, id=user_id)
            if user_obj == request.user:
                messages.error(request, 'No puedes desactivar tu propia cuenta en uso.')
            else:
                user_obj.is_active = not user_obj.is_active
                user_obj.save()
                estado_txt = 'activada' if user_obj.is_active else 'desactivada'
                messages.success(request, f'Cuenta {user_obj.email} {estado_txt}.')

        elif accion == 'desbloquear':
            user_id = request.POST.get('user_id')
            user_obj = get_object_or_404(Usuario, id=user_id)
            user_obj.bloqueado_hasta = None
            user_obj.save()
            messages.success(request, f'Sanción removida: {user_obj.email} ahora está desbloqueado.')

        elif accion == 'reset_password':
            user_id = request.POST.get('user_id')
            nueva_clave = request.POST.get('nueva_password', '')
            user_obj = get_object_or_404(Usuario, id=user_id)
            if len(nueva_clave) < 6:
                messages.error(request, 'La nueva contraseña debe tener al menos 6 caracteres.')
            else:
                user_obj.set_password(nueva_clave)
                user_obj.save()
                messages.success(request, f'Contraseña de {user_obj.email} restablecida correctamente.')

        elif accion == 'cambiar_estado_equipo':
            equipo_id = request.POST.get('equipo_id')
            nuevo_estado = request.POST.get('nuevo_estado')
            equipo_obj = get_object_or_404(Equipo, id=equipo_id)
            estado_antiguo = equipo_obj.get_estado_display()
            equipo_obj.estado = nuevo_estado
            equipo_obj.version += 1
            equipo_obj.save()
            messages.success(
                request,
                f'Estado del equipo "{equipo_obj.nombre}" ({equipo_obj.codigo_inventario}) '
                f'actualizado exitosamente de {estado_antiguo} a {equipo_obj.get_estado_display()}.'
            )

        return redirect('admin_panel')

    filtro_rol = request.GET.get('rol', '')
    busqueda = request.GET.get('q', '').strip()
    busqueda_equipo = request.GET.get('q_equipo', '').strip()
    filtro_estado_equipo = request.GET.get('estado_equipo', '').strip()

    qs = Usuario.objects.all().order_by('-date_joined')
    if filtro_rol:
        qs = qs.filter(rol=filtro_rol)
    if busqueda:
        qs = qs.filter(Q(email__icontains=busqueda) | Q(first_name__icontains=busqueda) | Q(last_name__icontains=busqueda))

    qs_equipos = Equipo.objects.all().order_by('nombre')
    if busqueda_equipo:
        qs_equipos = qs_equipos.filter(
            Q(codigo_inventario__icontains=busqueda_equipo) |
            Q(nombre__icontains=busqueda_equipo) |
            Q(modelo__icontains=busqueda_equipo)
        )
    if filtro_estado_equipo:
        qs_equipos = qs_equipos.filter(estado=filtro_estado_equipo)

    metricas = {
        'total_usuarios': Usuario.objects.count(),
        'estudiantes': Usuario.objects.filter(rol=Usuario.Rol.ESTUDIANTE).count(),
        'docentes': Usuario.objects.filter(rol=Usuario.Rol.DOCENTE).count(),
        'directores': Usuario.objects.filter(rol=Usuario.Rol.DIRECTOR_CARRERA).count(),
        'encargados': Usuario.objects.filter(rol=Usuario.Rol.ENCARGADO_LABORATORIO).count(),
        'control_calidad': Usuario.objects.filter(rol=Usuario.Rol.CONTROL_CALIDAD).count(),
        'bloqueados': Usuario.objects.filter(bloqueado_hasta__gt=timezone.now()).count(),
        'staff': Usuario.objects.filter(is_staff=True).count(),
        'equipos_total': Equipo.objects.count(),
        'equipos_disponibles': Equipo.objects.filter(estado=Equipo.Estado.DISPONIBLE).count(),
        'equipos_mantenimiento': Equipo.objects.filter(estado=Equipo.Estado.EN_MANTENIMIENTO).count(),
        'equipos_prestados': Equipo.objects.filter(estado=Equipo.Estado.PRESTADO).count(),
        'equipos_baja': Equipo.objects.filter(estado=Equipo.Estado.FUERA_SERVICIO).count(),
    }

    ultimos_movimientos = Movimiento.objects.select_related('solicitud', 'responsable').order_by('-fecha')[:10]

    return render(request, 'inventario/admin_panel.html', {
        'usuarios': qs,
        'equipos_admin': qs_equipos,
        'metricas': metricas,
        'roles_choices': Usuario.Rol.choices,
        'estados_equipos_choices': Equipo.Estado.choices,
        'filtro_rol': filtro_rol,
        'busqueda': busqueda,
        'busqueda_equipo': busqueda_equipo,
        'filtro_estado_equipo': filtro_estado_equipo,
        'ultimos_movimientos': ultimos_movimientos,
    })

