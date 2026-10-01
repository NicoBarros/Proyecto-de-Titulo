"""
Vistas de Django - Lógica de negocio equivalente a src/routes/ en Node.
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib import messages
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
    """RF-13: Dashboard de resumen."""
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
    """RF-01 a RF-04: Gestion de inventario."""
    puede_escribir = request.user.rol in Usuario.ROLES_ESCRITURA_INVENTARIO
    tab = request.GET.get('tab', 'equipos')
    
    context = {'puede_escribir': puede_escribir, 'tab': tab}
    
    if tab == 'equipos':
        context['equipos'] = Equipo.objects.all()
        if puede_escribir and request.method == 'POST' and 'codigo_inventario' in request.POST:
            form = EquipoForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, 'Equipo agregado exitosamente.')
                return redirect('/inventario/?tab=equipos')
            else:
                messages.error(request, 'Error al agregar equipo.')
    else:
        context['insumos'] = Insumo.objects.all()
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
            # Aumentamos la versión manual para el bloqueo optimista
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
    """RF-06, RF-07, RF-08, RF-09: Gestion de solicitudes."""
    puede_aprobar = request.user.rol in Usuario.ROLES_APROBADORES
    
    # Crear nueva solicitud (Soporte para Kits)
    if request.method == 'POST' and 'item[]' in request.POST:
        items = request.POST.getlist('item[]')
        cantidades = request.POST.getlist('cantidad[]')
        
        try:
            with transaction.atomic():
                # Crear la solicitud base
                solicitud = Solicitud.objects.create(
                    solicitante=request.user,
                    lugar_uso=request.POST.get('lugar_uso'),
                    justificacion=request.POST.get('justificacion'),
                    horario_inicio=request.POST.get('horario_inicio'),
                    horario_fin=request.POST.get('horario_fin'),
                )
                
                # Procesar cada ítem del Kit
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

    # Procesar acciones (Aprobar, Entregar, Devolver, Rechazar)
    if request.method == 'POST' and 'accion' in request.POST:
        if not puede_aprobar:
            messages.error(request, 'No tienes permiso para aprobar solicitudes.')
            return redirect('solicitudes')
            
        solicitud_id = request.POST.get('solicitud_id')
        accion = request.POST.get('accion')
        solicitud = get_object_or_404(Solicitud, id=solicitud_id)
        
        try:
            if accion == 'aprobar':
                # Validar choques de horario (RF-07)
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
                
                # RF-09: Bloqueo
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

    # GET datos para renderizar
    solicitudes = Solicitud.objects.all().prefetch_related('items', 'items__equipo', 'items__insumo')
    equipos = Equipo.objects.filter(estado=Equipo.Estado.DISPONIBLE)
    insumos = Insumo.objects.all()
    
    return render(request, 'inventario/solicitudes.html', {
        'solicitudes': solicitudes, 'equipos': equipos, 'insumos': insumos, 'puede_aprobar': puede_aprobar
    })


@login_required
@role_required(Usuario.Rol.ENCARGADO_LABORATORIO, Usuario.Rol.CONTROL_CALIDAD)
def mantenimiento_view(request):
    """RF-10: Mantenimiento y regla del 70%."""
    if request.method == 'POST':
        if 'decision' in request.POST:
            # Resolver
            mant_id = request.POST.get('mant_id')
            decision = request.POST.get('decision')
            mant = get_object_or_404(Mantenimiento, id=mant_id)
            mant.decision = decision
            mant.fecha_resolucion = timezone.now()
            mant.save()
            
            mant.equipo.estado = Equipo.Estado.FUERA_SERVICIO if decision == 'dar_baja' else Equipo.Estado.DISPONIBLE
            mant.equipo.version += 1
            mant.equipo.save()
            messages.success(request, f'Decisión confirmada: {mant.get_decision_display()}.')
        else:
            # Diagnosticar
            form = MantenimientoForm(request.POST)
            if form.is_valid():
                equipo = get_object_or_404(Equipo, id=form.cleaned_data['equipo_id'])
                costo = form.cleaned_data['costo_cotizado']
                
                porcentaje = costo / equipo.valor_adquisicion if equipo.valor_adquisicion else None
                sugerencia = Mantenimiento.Decision.DAR_BAJA if porcentaje and porcentaje >= 0.70 else Mantenimiento.Decision.REPARAR
                
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
                
                msg = f"Sugerencia del sistema: {sugerencia.upper()} "
                msg += f"(Costo representa {(porcentaje*100):.1f}% del valor)" if porcentaje else "(Falta valor de adquisición)"
                messages.info(request, msg)
                
        return redirect('mantenimiento')
        
    mantenimientos = Mantenimiento.objects.all().select_related('equipo')
    equipos = Equipo.objects.all()
    return render(request, 'inventario/mantenimiento.html', {'mantenimientos': mantenimientos, 'equipos': equipos})


@login_required
def reportes_view(request):
    """RF-13: Reportes."""
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


@login_required
def busqueda_view(request):
    """
    RF-11 / RNF-06: Busqueda por IA.
    Actualizado a Google Gemini.
    """
    if request.method == 'GET':
        return render(request, 'inventario/busqueda.html')
        
    consulta = request.POST.get('consulta')
    disponibles = list(Equipo.objects.filter(estado=Equipo.Estado.DISPONIBLE))
    
    if not consulta:
        return JsonResponse({'error': 'Falta consulta'}, status=400)
        
    resultados = []
    fuente = 'palabras_clave_local'
    
    # 1. Intentar con Gemini si hay API key
    if getattr(settings, 'GEMINI_API_KEY', None):
        try:
            from google import genai
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            
            catalogo = "\n".join([f"- id={e.id}: {e.nombre} ({e.modelo or 's/modelo'}) - {e.especificaciones or ''}" for e in disponibles])
            prompt = f"""Eres un asistente que ayuda a un encargado de laboratorio a encontrar equipos.
Catalogo de equipos disponibles:
{catalogo}

Necesidad del usuario: "{consulta}"

Responde SOLO con un JSON array de los ids de equipo mas relevantes (maximo 5), ordenados del mas al menos relevante. Ejemplo: [3, 1, 7]"""

            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
            )
            
            # Limpiar posible markdown en la respuesta
            text = response.text.replace('```json', '').replace('```', '').strip()
            ids = json.loads(text)
            
            if isinstance(ids, list):
                # Mantener orden
                for item_id in ids:
                    equipo = next((e for e in disponibles if e.id == item_id), None)
                    if equipo:
                        resultados.append({
                            'nombre': equipo.nombre, 'codigo_inventario': equipo.codigo_inventario, 
                            'estado': equipo.get_estado_display()
                        })
                fuente = 'ia_gemini'
        except Exception as e:
            print(f"Error llamando a Gemini: {e}")
            # Fallback a local continua abajo
    
    # 2. Fallback palabras clave
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
                'nombre': e.nombre, 'codigo_inventario': e.codigo_inventario, 
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
    # Escribir la cabecera idéntica a la esperada por RF-14
    writer.writerow(['tipo', 'codigo_inventario', 'nombre', 'modelo', 'especificaciones', 'ubicacion', 'estado', 'valor_adquisicion', 'categoria', 'tipo_insumo', 'cantidad'])

    # Exportar Equipos
    equipos = Equipo.objects.all()
    for e in equipos:
        writer.writerow(['equipo', e.codigo_inventario, e.nombre, e.modelo or '', e.especificaciones or '', e.ubicacion or '', e.estado, e.valor_adquisicion or '', '', '', ''])

    # Exportar Insumos
    insumos = Insumo.objects.all()
    for i in insumos:
        writer.writerow(['insumo', '', i.nombre, '', '', '', '', '', i.categoria or '', i.tipo, i.cantidad_total])

    return response
