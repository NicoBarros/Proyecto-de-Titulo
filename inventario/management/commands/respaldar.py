from django.conf import settings
from django.core.management.base import BaseCommand

from inventario.respaldos import aplicar_retencion, crear_respaldo, descripcion_base


class Command(BaseCommand):
    help = 'Genera un respaldo comprimido de la base de datos PostgreSQL con pg_dump.'

    def add_arguments(self, parser):
        parser.add_argument('--directorio', default=settings.RESPALDOS_DIR)
        parser.add_argument('--conservar', type=int, default=14)

    def handle(self, *args, directorio, conservar, **kwargs):
        origen = descripcion_base()
        destino, tablas, digest = crear_respaldo(directorio)
        self.stdout.write(self.style.SUCCESS(f'Respaldo de {origen} creado: {destino}'))
        self.stdout.write(f'  Tamaño:  {destino.stat().st_size / 1024:.1f} KB')
        self.stdout.write(f'  Tablas:  {tablas}')
        self.stdout.write(f'  SHA-256: {digest}')
        for eliminado in aplicar_retencion(directorio, conservar):
            self.stdout.write(f'Respaldo antiguo eliminado: {eliminado.name}')
