from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from inventario.models import Equipo, HistorialEquipo, Insumo, Mantenimiento, Solicitud, Usuario
from inventario.respaldos import base_postgres, descripcion_base, restaurar_respaldo, verificar_integridad


class Command(BaseCommand):
    help = 'Restaura un respaldo generado con el comando respaldar, reemplazando los datos actuales.'

    def add_arguments(self, parser):
        parser.add_argument('archivo')
        parser.add_argument('--noinput', '--no-input', action='store_false', dest='interactivo')

    def handle(self, *args, archivo, interactivo, **kwargs):
        ruta = Path(archivo)
        if not ruta.is_file():
            raise CommandError(f'No existe el archivo {ruta}.')
        nombre_base = base_postgres()['NAME']
        destino = descripcion_base()

        integro = verificar_integridad(ruta)
        if integro:
            self.stdout.write('Integridad verificada (SHA-256).')
        else:
            self.stdout.write(self.style.WARNING('El respaldo no tiene archivo .sha256: no se verificó su integridad.'))

        if interactivo:
            respuesta = input(
                f'Se reemplazarán todos los datos de {destino}. Escribe "{nombre_base}" para continuar: '
            )
            if respuesta.strip() != nombre_base:
                raise CommandError('Restauración cancelada.')

        restaurar_respaldo(ruta)
        self.stdout.write(self.style.SUCCESS(f'Respaldo {ruta.name} restaurado en {destino}.'))
        for etiqueta, modelo in (
            ('Usuarios', Usuario), ('Equipos', Equipo), ('Insumos', Insumo),
            ('Solicitudes', Solicitud), ('Mantenimientos', Mantenimiento), ('Historial', HistorialEquipo),
        ):
            self.stdout.write(f'  {etiqueta}: {modelo.objects.count()}')
