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

import secrets
from datetime import timedelta
from django.utils import timezone


class ISPUploadToken(models.Model):
    """Tokens únicos para que ISPs suban archivos sin acceso al sistema"""
    proveedor_nombre = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='Nombre del ISP'
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        editable=False,
        verbose_name='Token de acceso'
    )
    email_contacto = models.EmailField(
        blank=True,
        null=True,
        verbose_name='Email de contacto'
    )
    activo = models.BooleanField(
        default=True,
        verbose_name='¿Activo?'
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de creación'
    )
    fecha_expiracion = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Fecha de expiración (opcional)'
    )
    archivos_subidos = models.IntegerField(
        default=0,
        verbose_name='Total de archivos subidos'
    )
    ultima_subida = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Última subida'
    )

    class Meta:
        verbose_name = 'Token de ISP'
        verbose_name_plural = 'Tokens de ISPs'
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"{self.proveedor_nombre} - {'Activo' if self.activo else 'Inactivo'}"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    @property
    def is_valid(self):
        """Verifica si el token es válido"""
        if not self.activo:
            return False
        if self.fecha_expiracion and timezone.now() > self.fecha_expiracion:
            return False
        return True

    def get_upload_url(self):
        """Retorna la URL de upload para este ISP"""
        from django.conf import settings
        base_url = f"https://86.48.21.76"  # Cambiar cuando tengas dominio
        return f"{base_url}/cobertura/isp-upload/{self.token}/"


class BulkQueryJob(models.Model):
    """Jobs de consulta masiva de cobertura"""
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('processing', 'Procesando'),
        ('completed', 'Completado'),
        ('failed', 'Fallido'),
    ]

    usuario = models.ForeignKey(
        'Usuario',
        on_delete=models.CASCADE,
        related_name='bulk_queries',
        verbose_name='Usuario'
    )
    archivo_entrada = models.FileField(
        upload_to='bulk_queries/input/',
        verbose_name='Archivo CSV de entrada'
    )
    archivo_salida = models.FileField(
        upload_to='bulk_queries/output/',
        blank=True,
        null=True,
        verbose_name='Archivo CSV de salida'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Estado'
    )
    total_registros = models.IntegerField(
        default=0,
        verbose_name='Total de registros'
    )
    registros_procesados = models.IntegerField(
        default=0,
        verbose_name='Registros procesados'
    )
    fecha_creacion = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de creación'
    )
    fecha_inicio = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Fecha de inicio'
    )
    fecha_finalizacion = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Fecha de finalización'
    )
    error_mensaje = models.TextField(
        blank=True,
        null=True,
        verbose_name='Mensaje de error'
    )

    class Meta:
        verbose_name = 'Consulta Masiva'
        verbose_name_plural = 'Consultas Masivas'
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"Job #{self.id} - {self.usuario.username} - {self.status}"

    @property
    def progreso_porcentaje(self):
        """Calcula el porcentaje de progreso"""
        if self.total_registros == 0:
            return 0
        return int((self.registros_procesados / self.total_registros) * 100)

    @property
    def tiempo_estimado_segundos(self):
        """Estima el tiempo restante en segundos (aprox 0.5 seg por registro)"""
        if self.status == 'completed':
            return 0
        registros_restantes = self.total_registros - self.registros_procesados
        return registros_restantes * 0.5
