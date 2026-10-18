from django.core.management.base import BaseCommand

from inventario.models import Solicitud


class Command(BaseCommand):
    help = 'Marca como atrasadas las solicitudes entregadas cuyo horario de fin ya venció.'

    def handle(self, *args, **kwargs):
        marcadas = Solicitud.marcar_atrasadas()
        self.stdout.write(self.style.SUCCESS(f'Solicitudes marcadas como atrasadas: {marcadas}'))
