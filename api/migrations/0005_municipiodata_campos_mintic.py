from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0004_municipiodata_analisisFactibilidad'),
    ]

    operations = [
        migrations.AddField(
            model_name='municipiodata',
            name='mintic_accesos_reales',
            field=models.IntegerField(blank=True, null=True, verbose_name='Accesos fijos reales MinTIC'),
        ),
        migrations.AddField(
            model_name='municipiodata',
            name='mintic_proveedores_reales',
            field=models.IntegerField(blank=True, null=True, verbose_name='Proveedores reales MinTIC'),
        ),
        migrations.AddField(
            model_name='municipiodata',
            name='isps_directorio',
            field=models.TextField(blank=True, null=True, verbose_name='ISPs directorio (JSON)'),
        ),
    ]
