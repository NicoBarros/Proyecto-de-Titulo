from django.core.management.base import BaseCommand

from inventario import busqueda_semantica
from inventario.models import Equipo


class Command(BaseCommand):
    help = 'Descarga el modelo de búsqueda semántica si falta y genera los vectores de los equipos.'

    def handle(self, *args, **kwargs):
        _, actualizados = busqueda_semantica.indexar(Equipo.objects.all())
        self.stdout.write(f'Vectores actualizados: {actualizados}')
