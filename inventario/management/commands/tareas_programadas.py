from django.core.management.base import BaseCommand

from inventario import tareas


class Command(BaseCommand):
    help = (
        'Ejecuta las tareas periódicas: marca préstamos atrasados y equipos pendientes de baja, '
        'envía los avisos pendientes, actualiza el índice de búsqueda, genera el respaldo diario y evalúa la búsqueda cada mes.'
    )

    def handle(self, *args, **kwargs):
        for tarea, cantidad in tareas.ejecutar().items():
            self.stdout.write(f'{tarea}: {cantidad}')
