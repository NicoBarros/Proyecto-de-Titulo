from django.db import migrations


def convertir_atrasadas_devueltas(apps, schema_editor):
    Solicitud = apps.get_model('inventario', 'Solicitud')
    Solicitud.objects.filter(estado='atrasada', movimientos__tipo='devolucion').update(estado='devuelta_atraso')


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0006_historial_equipo'),
    ]

    operations = [
        migrations.RunPython(convertir_atrasadas_devueltas, migrations.RunPython.noop),
    ]
