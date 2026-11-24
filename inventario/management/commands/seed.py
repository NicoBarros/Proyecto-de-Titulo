"""
Comando para poblar la base de datos con datos de prueba enriquecidos.
Incluye:
- Usuarios institucionales (con todos los roles)
- Equipos con especificaciones, ubicación y valores de adquisición
- Insumos renovables y perecibles con umbrales de stock
- Solicitudes en distintos estados (Pendiente, Entregada, Atrasada, Devuelta, Devuelta con atraso)
- Mantenimiento aplicando la regla del 70 % (RF-10)
- Búsquedas con IA, brechas y evaluación mensual (RNF-11)
- Solicitud de derechos sobre datos personales (Ley N.° 21.719)
- Eventos de auditoría de equipos
"""
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from inventario.models import (
    BusquedaIA,
    Equipo,
    EvaluacionBusqueda,
    HistorialEquipo,
    Insumo,
    Mantenimiento,
    Movimiento,
    Solicitud,
    SolicitudDerecho,
    SolicitudItem,
    Usuario,
)


class Command(BaseCommand):
    help = 'Poblar la base de datos con datos de prueba enriquecidos (seed).'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.NOTICE('Iniciando carga de datos de prueba...'))
        ahora = timezone.now()
        hoy = timezone.localdate()

        # ── 1. Usuarios ─────────────────────────────────────────────────────────────
        usuarios_data = [
            {
                'email': 'encargado.leica@inacapmail.cl',
                'rol': Usuario.Rol.ENCARGADO_LABORATORIO,
                'first_name': 'Ana',
                'last_name': 'Soto',
                'is_staff': True,
                'is_superuser': True,
            },
            {
                'email': 'calidad@inacapmail.cl',
                'rol': Usuario.Rol.CONTROL_CALIDAD,
                'first_name': 'María',
                'last_name': 'Gómez',
                'is_staff': True,
            },
            {
                'email': 'dcarrera@inacapmail.cl',
                'rol': Usuario.Rol.DIRECTOR_CARRERA,
                'first_name': 'Roberto',
                'last_name': 'Paz',
            },
            {
                'email': 'docente1@inacapmail.cl',
                'rol': Usuario.Rol.DOCENTE,
                'first_name': 'Carlos',
                'last_name': 'Ruiz',
            },
            {
                'email': 'estudiante1@inacapmail.cl',
                'rol': Usuario.Rol.ESTUDIANTE,
                'first_name': 'Luis',
                'last_name': 'Pino',
                'seccion': 'TIN-401',
            },
            {
                'email': 'estudiante2@inacapmail.cl',
                'rol': Usuario.Rol.ESTUDIANTE,
                'first_name': 'Paula',
                'last_name': 'Vega',
                'seccion': 'TIN-401',
            },
            {
                'email': 'comite@inacapmail.cl',
                'rol': Usuario.Rol.COMITE_EJECUTIVO,
                'first_name': 'Felipe',
                'last_name': 'Bravo',
            },
        ]

        usuarios = {}
        for u in usuarios_data:
            email = u.pop('email')
            usuario, creado = Usuario.objects.get_or_create(
                email=email,
                defaults={
                    'username': email.split('@')[0],
                    'is_active': True,
                    **u,
                },
            )
            if creado:
                usuario.set_password('Leica2026!')
                usuario.save()
                self.stdout.write(self.style.SUCCESS(f'  ✓ Creado usuario: {email}'))
            usuarios[email] = usuario

        # ── 2. Equipos ──────────────────────────────────────────────────────────────
        equipos_data = [
            {
                'codigo_inventario': 'LTV-001',
                'nombre': 'Multímetro Digital',
                'modelo': 'Fluke 115',
                'especificaciones': 'True RMS, 600V, medición de capacitancia y continuidad',
                'ubicacion': 'Laboratorio LEICA - Estante A',
                'estado': Equipo.Estado.DISPONIBLE,
                'valor_adquisicion': Decimal('249990.00'),
                'fecha_adquisicion': hoy - timedelta(days=365 * 2),
            },
            {
                'codigo_inventario': 'LTV-002',
                'nombre': 'Osciloscopio Digital',
                'modelo': 'Tektronix TBS1052B',
                'especificaciones': '50 MHz, 2 canales, 1 GS/s de muestreo',
                'ubicacion': 'Laboratorio LEICA - Banco de Trabajo 2',
                'estado': Equipo.Estado.EN_MANTENIMIENTO,
                'valor_adquisicion': Decimal('649990.00'),
                'fecha_adquisicion': hoy - timedelta(days=365 * 3),
            },
            {
                'codigo_inventario': 'LTV-003',
                'nombre': 'Fuente de Poder Programable',
                'modelo': 'Rigol DP832',
                'especificaciones': '3 canales independientes, 30V/3A, bajo rizado',
                'ubicacion': 'Laboratorio LEICA - Banco de Trabajo 1',
                'estado': Equipo.Estado.PRESTADO,
                'valor_adquisicion': Decimal('420000.00'),
                'fecha_adquisicion': hoy - timedelta(days=365 * 2),
            },
            {
                'codigo_inventario': 'LTV-004',
                'nombre': 'Kit Router Cisco',
                'modelo': 'Cisco ISR 4221',
                'especificaciones': 'Para laboratorios de redes y telecomunicaciones CCNA',
                'ubicacion': 'Rack Telecomunicaciones 1',
                'estado': Equipo.Estado.DISPONIBLE,
                'valor_adquisicion': Decimal('890000.00'),
                'fecha_adquisicion': hoy - timedelta(days=365),
            },
            {
                'codigo_inventario': 'LTV-005',
                'nombre': 'Estación Total Topográfica',
                'modelo': 'Leica FlexLine TS07',
                'especificaciones': 'Precisión angular 2", medición sin prisma hasta 500m (fuera de sede)',
                'ubicacion': 'Bodega de Topografía',
                'estado': Equipo.Estado.DISPONIBLE,
                'valor_adquisicion': Decimal('4500000.00'),
                'fecha_adquisicion': hoy - timedelta(days=365 * 2),
            },
            {
                'codigo_inventario': 'LTV-006',
                'nombre': 'Switch Administrable',
                'modelo': 'Cisco Catalyst 2960-X',
                'especificaciones': '24 puertos Gigabit Ethernet, soporte VLAN y PoE+',
                'ubicacion': 'Rack Telecomunicaciones 2',
                'estado': Equipo.Estado.DISPONIBLE,
                'valor_adquisicion': Decimal('380000.00'),
                'fecha_adquisicion': hoy - timedelta(days=365 * 3),
            },
            {
                'codigo_inventario': 'LTV-007',
                'nombre': 'Estación de Soldadura',
                'modelo': 'Yihua 8786D',
                'especificaciones': 'Estación 2 en 1 con aire caliente y cautín digital ESD',
                'ubicacion': 'Mesa 3 - Electrónica',
                'estado': Equipo.Estado.DISPONIBLE,
                'valor_adquisicion': Decimal('95000.00'),
                'fecha_adquisicion': hoy - timedelta(days=180),
            },
        ]

        equipos = {}
        for eq_data in equipos_data:
            codigo = eq_data.pop('codigo_inventario')
            equipo, creado = Equipo.objects.get_or_create(
                codigo_inventario=codigo,
                defaults=eq_data,
            )
            if creado:
                self.stdout.write(self.style.SUCCESS(f'  ✓ Creado equipo: {equipo.nombre} ({codigo})'))
            equipos[codigo] = equipo

        # ── 3. Insumos ──────────────────────────────────────────────────────────────
        insumos_data = [
            {
                'nombre': 'Cables de prueba con caimán (par)',
                'categoria': 'Cables',
                'tipo': Insumo.Tipo.RENOVABLE,
                'cantidad_total': 20,
                'cantidad_disponible': 18,
                'umbral_minimo': 5,
            },
            {
                'nombre': 'Protoboard 830 puntos',
                'categoria': 'Componentes',
                'tipo': Insumo.Tipo.RENOVABLE,
                'cantidad_total': 15,
                'cantidad_disponible': 13,
                'umbral_minimo': 3,
            },
            {
                'nombre': 'Resistencias 1k ohm 1/4W (pack 100)',
                'categoria': 'Consumibles',
                'tipo': Insumo.Tipo.PERECIBLE,
                'cantidad_total': 50,
                'cantidad_disponible': 42,
                'umbral_minimo': 10,
            },
            {
                'nombre': 'Patch Cord Cat6 UTP (1.5m)',
                'categoria': 'Cables',
                'tipo': Insumo.Tipo.RENOVABLE,
                'cantidad_total': 30,
                'cantidad_disponible': 4,  # Stock bajo intencional para alertar en Dashboard
                'umbral_minimo': 8,
            },
        ]

        insumos = {}
        for ins_data in insumos_data:
            nombre = ins_data.pop('nombre')
            insumo, creado = Insumo.objects.get_or_create(nombre=nombre, defaults=ins_data)
            if creado:
                self.stdout.write(self.style.SUCCESS(f'  ✓ Creado insumo: {nombre}'))
            insumos[nombre] = insumo

        # ── 4. Solicitudes con Historia ─────────────────────────────────────────────
        # Solicitud 1: Pendiente (creada por docente en representación de estudiante1)
        if not Solicitud.objects.filter(justificacion='Práctica de laboratorio de mediciones electrónicas').exists():
            s_pen = Solicitud.objects.create(
                solicitante=usuarios['docente1@inacapmail.cl'],
                en_representacion_de=usuarios['estudiante1@inacapmail.cl'],
                lugar_uso=Solicitud.LugarUso.DENTRO_SEDE,
                justificacion='Práctica de laboratorio de mediciones electrónicas',
                horario_inicio=ahora + timedelta(hours=2),
                horario_fin=ahora + timedelta(hours=5),
                estado=Solicitud.EstadoSolicitud.PENDIENTE,
            )
            SolicitudItem.objects.create(solicitud=s_pen, equipo=equipos['LTV-001'], cantidad=1)
            SolicitudItem.objects.create(solicitud=s_pen, insumo=insumos['Cables de prueba con caimán (par)'], cantidad=1)
            self.stdout.write(self.style.SUCCESS('  ✓ Creada solicitud pendiente (#1)'))

        # Solicitud 2: Atrasada (entregada a estudiante2 y venció ayer)
        if not Solicitud.objects.filter(justificacion='Proyecto de fuentes conmutadas').exists():
            s_atrasada = Solicitud.objects.create(
                solicitante=usuarios['estudiante2@inacapmail.cl'],
                lugar_uso=Solicitud.LugarUso.DENTRO_SEDE,
                justificacion='Proyecto de fuentes conmutadas',
                horario_inicio=ahora - timedelta(days=2),
                horario_fin=ahora - timedelta(hours=18),
                estado=Solicitud.EstadoSolicitud.ATRASADA,
                aprobado_por=usuarios['encargado.leica@inacapmail.cl'],
                fecha_aprobacion=ahora - timedelta(days=2),
                revisada_en=ahora - timedelta(days=2),
            )
            SolicitudItem.objects.create(solicitud=s_atrasada, equipo=equipos['LTV-003'], cantidad=1)
            Movimiento.objects.create(
                solicitud=s_atrasada,
                tipo=Movimiento.TipoMovimiento.ENTREGA,
                responsable=usuarios['encargado.leica@inacapmail.cl'],
                observacion='Entregado en perfecto estado',
            )
            self.stdout.write(self.style.SUCCESS('  ✓ Creada solicitud atrasada (#2)'))

        # Solicitud 3: Devuelta con atraso (completada hace 3 días)
        if not Solicitud.objects.filter(justificacion='Configuración de switches y VLANs').exists():
            s_dev_atraso = Solicitud.objects.create(
                solicitante=usuarios['estudiante1@inacapmail.cl'],
                lugar_uso=Solicitud.LugarUso.DENTRO_SEDE,
                justificacion='Configuración de switches y VLANs',
                horario_inicio=ahora - timedelta(days=6),
                horario_fin=ahora - timedelta(days=4),
                estado=Solicitud.EstadoSolicitud.DEVUELTA_ATRASO,
                aprobado_por=usuarios['encargado.leica@inacapmail.cl'],
                fecha_aprobacion=ahora - timedelta(days=6),
                revisada_en=ahora - timedelta(days=6),
            )
            item_dev = SolicitudItem.objects.create(
                solicitud=s_dev_atraso,
                equipo=equipos['LTV-006'],
                cantidad=1,
                estado_devolucion=SolicitudItem.EstadoDevolucion.BUENO,
            )
            Movimiento.objects.create(
                solicitud=s_dev_atraso,
                tipo=Movimiento.TipoMovimiento.ENTREGA,
                responsable=usuarios['encargado.leica@inacapmail.cl'],
            )
            Movimiento.objects.create(
                solicitud=s_dev_atraso,
                tipo=Movimiento.TipoMovimiento.DEVOLUCION,
                responsable=usuarios['encargado.leica@inacapmail.cl'],
                estado_equipo=item_dev.estado_devolucion,
                observacion='Devuelto con retraso justificado por corte de energía',
            )
            self.stdout.write(self.style.SUCCESS('  ✓ Creada solicitud devuelta con atraso (#3)'))

        # ── 5. Mantenimiento con Regla del 70 % (RF-10) ─────────────────────────────
        # Osciloscopio valor 649.990, cotización 520.000 (> 70 % -> sugerencia DAR DE BAJA)
        eq_osciloscopio = equipos['LTV-002']
        if not Mantenimiento.objects.filter(equipo=eq_osciloscopio).exists():
            Mantenimiento.objects.create(
                equipo=eq_osciloscopio,
                falla_descrita='Canal 1 en cortocircuito tras sobretensión accidental; tarjeta analógica dañada.',
                costo_cotizado=Decimal('520000.00'),
                porcentaje_costo=Decimal('0.8000'),
                decision=Mantenimiento.Decision.DAR_BAJA,
                reportado_por=usuarios['calidad@inacapmail.cl'],
            )
            self.stdout.write(self.style.SUCCESS('  ✓ Creado mantenimiento con regla del 70 % (LTV-002)'))

        # ── 6. Historial y Auditoría de Equipos ─────────────────────────────────────
        if not HistorialEquipo.objects.filter(codigo_inventario='LTV-002').exists():
            HistorialEquipo.objects.create(
                equipo=eq_osciloscopio,
                codigo_inventario='LTV-002',
                usuario=usuarios['calidad@inacapmail.cl'],
                accion=HistorialEquipo.Accion.ESTADO,
                cambios={'estado': ['disponible', 'en_mantenimiento']},
                detalle='Ingresado a mantenimiento por falla en canal 1',
            )

        # ── 7. Búsquedas con IA y KPIs (Supervisión y Brechas) ──────────────────────
        if not BusquedaIA.objects.exists():
            # Búsqueda 1: Exitosa con IA y respuesta generada
            BusquedaIA.objects.create(
                usuario=usuarios['estudiante1@inacapmail.cl'],
                consulta='necesito medir voltaje y continuidad en un circuito',
                fuente=BusquedaIA.Fuente.HIBRIDA,
                resultados=1,
                duracion_ms=145,
                equipo_elegido=equipos['LTV-001'],
                elegida_en=ahora - timedelta(days=3),
                generacion=BusquedaIA.Generacion.GENERADA,
                contexto=[equipos['LTV-001'].id],
                respuesta='Para medir voltaje y verificar continuidad se recomienda el [E1] Multímetro Digital Fluke 115.',
                citas=['E1'],
                duracion_generacion_ms=1250,
                util=True,
                calificada_en=ahora - timedelta(days=3),
            )
            # Búsqueda 2: Brecha de inventario (consulta sin resultados para el reporte)
            BusquedaIA.objects.create(
                usuario=usuarios['docente1@inacapmail.cl'],
                consulta='impresora 3D de resina fotosensible',
                fuente=BusquedaIA.Fuente.HIBRIDA,
                resultados=0,
                duracion_ms=90,
                generacion=BusquedaIA.Generacion.SIN_GENERACION,
                contexto=[],
                util=False,
                calificada_en=ahora - timedelta(days=2),
            )
            self.stdout.write(self.style.SUCCESS('  ✓ Creadas búsquedas con IA y brechas de reporte'))

        # ── 8. Evaluación de Búsqueda Mensual (RNF-11) ──────────────────────────────
        if not EvaluacionBusqueda.objects.exists():
            EvaluacionBusqueda.objects.create(
                ejecutada_por=usuarios['encargado.leica@inacapmail.cl'],
                metodo=BusquedaIA.Fuente.HIBRIDA,
                consultas=30,
                aciertos=27,
                duracion_ms=2850,
                detalle=[
                    {'consulta': 'necesito medir voltaje y continuidad en un circuito', 'posicion': 1, 'esperado': ['Multímetro']},
                    {'consulta': 'ver la forma de onda de una señal', 'posicion': 1, 'esperado': ['Osciloscopio']},
                    {'consulta': 'equipo para prácticas de enrutamiento', 'posicion': 1, 'esperado': ['Router Cisco']},
                ],
            )
            self.stdout.write(self.style.SUCCESS('  ✓ Registrada evaluación de búsqueda RNF-11 (27/30 - 90 %)'))

        # ── 9. Solicitud de Derechos sobre Datos Personales (Ley N.° 21.719) ─────────
        if not SolicitudDerecho.objects.exists():
            SolicitudDerecho.objects.create(
                usuario=usuarios['estudiante1@inacapmail.cl'],
                identificador='estudiante1@inacapmail.cl',
                tipo=SolicitudDerecho.Tipo.RECTIFICACION,
                detalle='Solicito corregir mi segundo apellido registrado en el sistema institucional.',
                estado=SolicitudDerecho.Estado.PENDIENTE,
            )
            self.stdout.write(self.style.SUCCESS('  ✓ Creada solicitud de derecho de datos personales (Ley 21.719)'))

        self.stdout.write(self.style.SUCCESS('\n========================================================'))
        self.stdout.write(self.style.SUCCESS('  Base de datos poblada exitosamente (Seed enriquecido).'))
        self.stdout.write(self.style.SUCCESS('========================================================\n'))
