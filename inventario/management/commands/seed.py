"""
Comando para poblar la base de datos con datos de prueba (usuarios, equipos, insumos).
"""
from django.core.management.base import BaseCommand
from inventario.models import Usuario, Equipo, Insumo

class Command(BaseCommand):
    help = 'Poblar la base de datos con datos de prueba (seed).'

    def handle(self, *args, **kwargs):
        # 1. Usuarios
        usuarios = [
            {'email': 'encargado.leica@inacapmail.cl', 'rol': Usuario.Rol.ENCARGADO_LABORATORIO, 'first_name': 'Ana Soto', 'is_staff': True, 'is_superuser': True},
            {'email': 'docente1@inacapmail.cl', 'rol': Usuario.Rol.DOCENTE, 'first_name': 'Carlos Ruiz', 'is_staff': True},
            {'email': 'calidad@inacapmail.cl', 'rol': Usuario.Rol.CONTROL_CALIDAD, 'first_name': 'María Gómez', 'is_staff': True},
            {'email': 'dcarrera@inacapmail.cl', 'rol': Usuario.Rol.DIRECTOR_CARRERA, 'first_name': 'Roberto Paz', 'is_staff': True},
            {'email': 'estudiante1@inacapmail.cl', 'rol': Usuario.Rol.ESTUDIANTE, 'first_name': 'Luis Pino', 'seccion': 'TIN-401'},
            {'email': 'estudiante2@inacapmail.cl', 'rol': Usuario.Rol.ESTUDIANTE, 'first_name': 'Paula Vega', 'seccion': 'TIN-401'},
        ]
        for u_data in usuarios:
            email = u_data.pop('email')
            if not Usuario.objects.filter(email=email).exists():
                user = Usuario.objects.create_user(
                    username=email.split('@')[0],
                    email=email,
                    password='Leica2026!',
                    **u_data
                )
                self.stdout.write(self.style.SUCCESS(f'Creado usuario: {email}'))

        # 2. Equipos
        equipos = [
            {'codigo_inventario': 'LTV-001', 'nombre': 'Multímetro Digital', 'modelo': 'Fluke 115', 'especificaciones': 'True RMS, 600V'},
            {'codigo_inventario': 'LTV-002', 'nombre': 'Osciloscopio', 'modelo': 'Tektronix TBS1052B', 'especificaciones': '50 MHz, 2 canales'},
            {'codigo_inventario': 'LTV-003', 'nombre': 'Fuente de Poder', 'modelo': 'Rigol DP832', 'especificaciones': 'Programable, 3 canales'},
            {'codigo_inventario': 'LTV-004', 'nombre': 'Kit Router Cisco', 'modelo': 'Cisco 4221', 'especificaciones': 'Para laboratorios de redes'},
            {'codigo_inventario': 'LTV-005', 'nombre': 'Estación Total', 'modelo': 'Leica TS07', 'especificaciones': 'Para topografía (fuera de sede)'},
            {'codigo_inventario': 'LTV-006', 'nombre': 'Switch Administrable', 'modelo': 'Cisco Catalyst 2960', 'especificaciones': '24 puertos Gigabit'},
        ]
        for e_data in equipos:
            obj, created = Equipo.objects.get_or_create(codigo_inventario=e_data['codigo_inventario'], defaults=e_data)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Creado equipo: {obj.nombre}'))

        # 3. Insumos
        insumos = [
            {'nombre': 'Cables de prueba (par)', 'categoria': 'Cables', 'tipo': Insumo.Tipo.RENOVABLE, 'cantidad_total': 20, 'cantidad_disponible': 20, 'umbral_minimo': 5},
            {'nombre': 'Protoboard 830 puntos', 'categoria': 'Componentes', 'tipo': Insumo.Tipo.RENOVABLE, 'cantidad_total': 15, 'cantidad_disponible': 15, 'umbral_minimo': 3},
            {'nombre': 'Resistencias 1k ohm', 'categoria': 'Consumibles', 'tipo': Insumo.Tipo.PERECIBLE, 'cantidad_total': 500, 'cantidad_disponible': 500, 'umbral_minimo': 50},
            {'nombre': 'Patch Cord Cat6 (1m)', 'categoria': 'Cables', 'tipo': Insumo.Tipo.RENOVABLE, 'cantidad_total': 30, 'cantidad_disponible': 30, 'umbral_minimo': 10},
        ]
        for i_data in insumos:
            obj, created = Insumo.objects.get_or_create(nombre=i_data['nombre'], defaults=i_data)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Creado insumo: {obj.nombre}'))
                
        self.stdout.write(self.style.SUCCESS('\nBase de datos poblada exitosamente (Seed completo).'))
