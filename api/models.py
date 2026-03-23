from django.contrib.gis.db import models
from django.contrib.auth.models import AbstractUser


class Usuario(AbstractUser):
    """Usuario personalizado para el sistema de cobertura"""
    telefono = models.CharField(max_length=20, blank=True, null=True)
    empresa = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return f"{self.username} - {self.get_full_name()}"


class CoberturaISP(models.Model):
    """Modelo para almacenar las coberturas de ISPs"""
    nombre = models.CharField(max_length=255, blank=True, null=True)
    descripcion = models.TextField(blank=True, null=True)
    proveedor = models.CharField(max_length=100, blank=True, null=True)
    tipo_servicio = models.CharField(max_length=50, blank=True, null=True)
    velocidad = models.CharField(max_length=50, blank=True, null=True)
    archivo_origen = models.CharField(max_length=255, blank=True, null=True)
    geom = models.GeometryField(srid=4326)
    fecha_importacion = models.DateTimeField(auto_now_add=True)
    usuario_subida = models.ForeignKey(
        'Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='archivos_subidos',
        verbose_name='Usuario que subió'
    )
    archivo_fisico = models.FileField(
        upload_to='uploads/kmz/',
        null=True,
        blank=True,
        verbose_name='Archivo KMZ original'
    )

    class Meta:
        db_table = 'cobertura_isp'
        verbose_name = 'Cobertura ISP'
        verbose_name_plural = 'Coberturas ISP'
        indexes = [
            models.Index(fields=['proveedor']),
            models.Index(fields=['archivo_origen']),
        ]

    def __str__(self):
        return f"{self.proveedor or 'Sin proveedor'} - {self.nombre or 'Sin nombre'}"