from django.core.management.base import BaseCommand

from inventario import tareas


class Command(BaseCommand):
    help = 'Ejecuta las tareas periódicas: marca préstamos atrasados y envía los avisos pendientes.'

    def handle(self, *args, **kwargs):
        for tarea, cantidad in tareas.ejecutar().items():
            self.stdout.write(f'{tarea}: {cantidad}')
