from django.core.management.base import BaseCommand

from inventario import evaluacion_busqueda


class Command(BaseCommand):
    help = 'Evalúa la búsqueda con las consultas de referencia: el equipo correcto debe quedar entre los 5 primeros.'

    def add_arguments(self, parser):
        parser.add_argument('--consultas', help='Archivo JSON con las consultas de referencia.')

    def handle(self, *args, **options):
        consultas = evaluacion_busqueda.cargar_consultas(options['consultas'])
        evaluacion = evaluacion_busqueda.evaluar(consultas)
        for d in evaluacion.detalle:
            marca = f"#{d['posicion']}" if d['posicion'] else 'FALLA'
            self.stdout.write(f"{marca:>6}  {d['consulta']}  ->  {', '.join(d['obtenidos']) or 'sin resultados'}")
        resumen = (
            f'{evaluacion.aciertos} de {evaluacion.consultas} consultas '
            f'({evaluacion.porcentaje or 0:.1f} %, meta {evaluacion.META} %) '
            f'con {evaluacion.get_metodo_display().lower()}'
        )
        estilo = self.style.SUCCESS if evaluacion.cumple else self.style.ERROR
        self.stdout.write(estilo(('Cumple: ' if evaluacion.cumple else 'No cumple: ') + resumen))
