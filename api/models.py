from django.conf import settings
from django.contrib.gis.db import models


class CoberturaISP(models.Model):
    """Modelo para almacenar cobertura geografica de ISPs."""

    nombre = models.CharField(max_length=255, blank=True, null=True)
    descripcion = models.TextField(blank=True, null=True)
    proveedor = models.CharField(max_length=100, blank=True, null=True)
    tipo_servicio = models.CharField(max_length=50, blank=True, null=True)
    velocidad = models.CharField(max_length=50, blank=True, null=True)
    archivo_origen = models.CharField(max_length=255, blank=True, null=True)
    geom = models.GeometryField(srid=4326)
    fecha_importacion = models.DateTimeField(auto_now_add=True)
    usuario_subida = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="archivos_subidos",
        verbose_name="Usuario que subio",
    )
    archivo_fisico = models.FileField(
        upload_to="uploads/kmz/",
        null=True,
        blank=True,
        verbose_name="Archivo KMZ original",
    )

    class Meta:
        db_table = "cobertura_isp"
        verbose_name = "Cobertura ISP"
        verbose_name_plural = "Coberturas ISP"
        indexes = [
            models.Index(fields=["proveedor"]),
            models.Index(fields=["archivo_origen"]),
        ]

    def __str__(self):
        proveedor = self.proveedor or "Sin proveedor"
        nombre = self.nombre or "Sin nombre"
        return f"{proveedor} - {nombre}"
