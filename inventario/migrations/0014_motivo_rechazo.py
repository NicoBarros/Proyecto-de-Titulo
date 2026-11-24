from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0013_kpi_busquedas_conflictos'),
    ]

    operations = [
        migrations.AddField(
            model_name='solicitud',
            name='motivo_rechazo',
            field=models.TextField(blank=True, default='', verbose_name='Motivo del rechazo'),
        ),
    ]
