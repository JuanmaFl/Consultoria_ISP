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

import hashlib
import json
from django.utils import timezone
from datetime import timedelta


class MunicipioData(models.Model):
    """Cache de datos públicos DANE + MinTIC por municipio"""
    codigo_dane = models.CharField(max_length=10, unique=True, verbose_name='Código DANE')
    nombre = models.CharField(max_length=150, verbose_name='Nombre municipio')
    departamento = models.CharField(max_length=100, verbose_name='Departamento')
    poblacion_total = models.IntegerField(blank=True, null=True, verbose_name='Población total')
    hogares = models.IntegerField(blank=True, null=True, verbose_name='Total hogares')
    nbi_porcentaje = models.FloatField(blank=True, null=True, verbose_name='% NBI')
    area_km2 = models.FloatField(blank=True, null=True, verbose_name='Área km²')
    densidad_poblacional = models.FloatField(blank=True, null=True, verbose_name='Densidad hab/km²')
    mintic_tiene_fibra = models.BooleanField(default=False, verbose_name='Tiene fibra según MinTIC')
    mintic_proveedores_count = models.IntegerField(default=0, verbose_name='Proveedores MinTIC')
    mintic_penetracion_pct = models.FloatField(blank=True, null=True, verbose_name='% penetración internet')
    latitud = models.FloatField(blank=True, null=True)
    longitud = models.FloatField(blank=True, null=True)
    mintic_accesos_reales = models.IntegerField(blank=True, null=True, verbose_name='Accesos fijos reales MinTIC')
    mintic_proveedores_reales = models.IntegerField(blank=True, null=True, verbose_name='Proveedores reales MinTIC')
    isps_directorio = models.TextField(blank=True, null=True, verbose_name='ISPs directorio (JSON)')
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Datos Municipio'
        verbose_name_plural = 'Datos Municipios'
        db_table = 'municipio_data'
        ordering = ['departamento', 'nombre']

    def __str__(self):
        return f"{self.nombre} ({self.departamento})"


class AnalisisFactibilidad(models.Model):
    """Análisis de factibilidad generado por OpenAI, cacheado 7 días"""

    TIPO_ZONA_CHOICES = [
        ('municipio', 'Municipio'),
        ('departamento', 'Departamento'),
        ('radio', 'Radio desde punto'),
    ]

    RECOMENDACION_CHOICES = [
        ('alta', 'Alta factibilidad'),
        ('media', 'Factibilidad media'),
        ('baja', 'Baja factibilidad'),
        ('saturada', 'Zona saturada'),
    ]

    usuario = models.ForeignKey('Usuario', on_delete=models.SET_NULL, null=True, verbose_name='Usuario')
    tipo_zona = models.CharField(max_length=20, choices=TIPO_ZONA_CHOICES, verbose_name='Tipo de zona')
    zona_nombre = models.CharField(max_length=200, verbose_name='Nombre de la zona')
    zona_parametros = models.JSONField(verbose_name='Parámetros de la zona')
    cache_hash = models.CharField(max_length=64, unique=True, verbose_name='Hash para cache')

    # Datos de cobertura ISP en la zona
    cobertura_isp_count = models.IntegerField(default=0, verbose_name='Registros ISP en zona')
    isps_presentes = models.JSONField(default=list, verbose_name='ISPs con cobertura')
    km_fibra_estimados = models.FloatField(blank=True, null=True, verbose_name='Km fibra estimados')

    # Datos demográficos
    poblacion_zona = models.IntegerField(blank=True, null=True, verbose_name='Población en zona')
    hogares_zona = models.IntegerField(blank=True, null=True, verbose_name='Hogares en zona')
    penetracion_actual_pct = models.FloatField(blank=True, null=True, verbose_name='% penetración actual')

    # Resultado IA
    analisis_texto = models.TextField(verbose_name='Análisis generado por IA')
    score_factibilidad = models.IntegerField(blank=True, null=True, verbose_name='Score factibilidad 0-100')
    recomendacion = models.CharField(max_length=20, choices=RECOMENDACION_CHOICES, blank=True, null=True)

    fecha_generacion = models.DateTimeField(auto_now_add=True)
    fecha_expiracion = models.DateTimeField(verbose_name='Expira el')

    class Meta:
        verbose_name = 'Análisis de Factibilidad'
        verbose_name_plural = 'Análisis de Factibilidad'
        db_table = 'analisis_factibilidad'
        ordering = ['-fecha_generacion']

    def __str__(self):
        return f"{self.zona_nombre} — {self.recomendacion} ({self.score_factibilidad}/100)"

    @property
    def esta_vigente(self):
        return timezone.now() < self.fecha_expiracion

    @staticmethod
    def generar_hash(tipo_zona, zona_parametros):
        contenido = json.dumps({'tipo': tipo_zona, 'params': zona_parametros}, sort_keys=True)
        return hashlib.sha256(contenido.encode()).hexdigest()

    @staticmethod
    def get_cache_vigente(tipo_zona, zona_parametros):
        """Retorna análisis cacheado si existe y no expiró"""
        cache_hash = AnalisisFactibilidad.generar_hash(tipo_zona, zona_parametros)
        try:
            analisis = AnalisisFactibilidad.objects.get(cache_hash=cache_hash)
            if analisis.esta_vigente:
                return analisis
            analisis.delete()
            return None
        except AnalisisFactibilidad.DoesNotExist:
            return None
