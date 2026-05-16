from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0003_ispuploadtoken_bulkqueryjob'),
    ]

    operations = [
        migrations.CreateModel(
            name='MunicipioData',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo_dane', models.CharField(max_length=10, unique=True, verbose_name='Código DANE')),
                ('nombre', models.CharField(max_length=150, verbose_name='Nombre municipio')),
                ('departamento', models.CharField(max_length=100, verbose_name='Departamento')),
                ('poblacion_total', models.IntegerField(blank=True, null=True, verbose_name='Población total')),
                ('hogares', models.IntegerField(blank=True, null=True, verbose_name='Total hogares')),
                ('nbi_porcentaje', models.FloatField(blank=True, null=True, verbose_name='% NBI')),
                ('area_km2', models.FloatField(blank=True, null=True, verbose_name='Área km²')),
                ('densidad_poblacional', models.FloatField(blank=True, null=True, verbose_name='Densidad hab/km²')),
                ('mintic_tiene_fibra', models.BooleanField(default=False, verbose_name='Tiene fibra según MinTIC')),
                ('mintic_proveedores_count', models.IntegerField(default=0, verbose_name='Proveedores MinTIC')),
                ('mintic_penetracion_pct', models.FloatField(blank=True, null=True, verbose_name='% penetración internet')),
                ('latitud', models.FloatField(blank=True, null=True)),
                ('longitud', models.FloatField(blank=True, null=True)),
                ('fecha_actualizacion', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Datos Municipio',
                'verbose_name_plural': 'Datos Municipios',
                'db_table': 'municipio_data',
                'ordering': ['departamento', 'nombre'],
            },
        ),
        migrations.CreateModel(
            name='AnalisisFactibilidad',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('tipo_zona', models.CharField(choices=[('municipio', 'Municipio'), ('departamento', 'Departamento'), ('radio', 'Radio desde punto')], max_length=20, verbose_name='Tipo de zona')),
                ('zona_nombre', models.CharField(max_length=200, verbose_name='Nombre de la zona')),
                ('zona_parametros', models.JSONField(verbose_name='Parámetros de la zona')),
                ('cache_hash', models.CharField(max_length=64, unique=True, verbose_name='Hash para cache')),
                ('cobertura_isp_count', models.IntegerField(default=0, verbose_name='Registros ISP en zona')),
                ('isps_presentes', models.JSONField(default=list, verbose_name='ISPs con cobertura')),
                ('km_fibra_estimados', models.FloatField(blank=True, null=True, verbose_name='Km fibra estimados')),
                ('poblacion_zona', models.IntegerField(blank=True, null=True, verbose_name='Población en zona')),
                ('hogares_zona', models.IntegerField(blank=True, null=True, verbose_name='Hogares en zona')),
                ('penetracion_actual_pct', models.FloatField(blank=True, null=True, verbose_name='% penetración actual')),
                ('analisis_texto', models.TextField(verbose_name='Análisis generado por IA')),
                ('score_factibilidad', models.IntegerField(blank=True, null=True, verbose_name='Score factibilidad 0-100')),
                ('recomendacion', models.CharField(blank=True, choices=[('alta', 'Alta factibilidad'), ('media', 'Factibilidad media'), ('baja', 'Baja factibilidad'), ('saturada', 'Zona saturada')], max_length=20, null=True)),
                ('fecha_generacion', models.DateTimeField(auto_now_add=True)),
                ('fecha_expiracion', models.DateTimeField(verbose_name='Expira el')),
                ('usuario', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='api.usuario', verbose_name='Usuario')),
            ],
            options={
                'verbose_name': 'Análisis de Factibilidad',
                'verbose_name_plural': 'Análisis de Factibilidad',
                'db_table': 'analisis_factibilidad',
                'ordering': ['-fecha_generacion'],
            },
        ),
    ]
