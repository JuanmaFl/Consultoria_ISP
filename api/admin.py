from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.gis.admin import GISModelAdmin
from django.utils.html import format_html
from django.urls import reverse
from .models import Usuario, CoberturaISP, ISPUploadToken, BulkQueryJob


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    """Admin personalizado para usuarios"""
    list_display = ['username', 'email', 'first_name', 'last_name', 'empresa', 'is_staff', 'is_active']
    list_filter = ['is_staff', 'is_active', 'empresa']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'empresa']
    
    fieldsets = UserAdmin.fieldsets + (
        ('Información adicional', {
            'fields': ('telefono', 'empresa')
        }),
    )
    
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Información adicional', {
            'fields': ('email', 'first_name', 'last_name', 'telefono', 'empresa')
        }),
    )


@admin.register(CoberturaISP)
class CoberturaISPAdmin(GISModelAdmin):
    """Admin para coberturas ISP con opción de eliminar archivos"""
    list_display = ['nombre', 'proveedor', 'archivo_origen', 'usuario_subida', 'fecha_importacion', 'eliminar_archivo']
    list_filter = ['proveedor', 'archivo_origen', 'usuario_subida', 'fecha_importacion']
    search_fields = ['nombre', 'descripcion', 'proveedor', 'archivo_origen']
    readonly_fields = ['fecha_importacion']
    actions = ['eliminar_archivos_kmz']
    
    fieldsets = (
        ('Información General', {
            'fields': ('nombre', 'descripcion', 'proveedor', 'tipo_servicio', 'velocidad')
        }),
        ('Archivo', {
            'fields': ('archivo_origen', 'archivo_fisico', 'usuario_subida')
        }),
        ('Geometría', {
            'fields': ('geom',)
        }),
        ('Metadatos', {
            'fields': ('fecha_importacion',)
        }),
    )
    
    gis_widget_kwargs = {
        'attrs': {
            'default_zoom': 12,
            'default_lon': -75.5636,
            'default_lat': 6.2476,
        },
    }
    
    def eliminar_archivo(self, obj):
        """Botón para eliminar archivo KMZ individual"""
        if obj.archivo_origen:
            return format_html(
                '<a class="button" href="{}">Eliminar</a>',
                reverse('admin:api_coberturaisp_delete', args=[obj.pk])
            )
        return '-'
    eliminar_archivo.short_description = 'Acciones'
    
    def eliminar_archivos_kmz(self, request, queryset):
        """Acción para eliminar múltiples archivos KMZ"""
        archivos_unicos = queryset.values_list('archivo_origen', flat=True).distinct()
        total_eliminados = 0
        
        for archivo in archivos_unicos:
            count = CoberturaISP.objects.filter(archivo_origen=archivo).delete()[0]
            total_eliminados += count
        
        self.message_user(
            request,
            f'{total_eliminados} registros eliminados de {len(archivos_unicos)} archivos KMZ.'
        )
    eliminar_archivos_kmz.short_description = 'Eliminar archivos KMZ seleccionados'
    
    def save_model(self, request, obj, form, change):
        """Guardar el usuario que modificó el registro"""
        if not change:
            obj.usuario_subida = request.user
        super().save_model(request, obj, form, change)


@admin.register(ISPUploadToken)
class ISPUploadTokenAdmin(admin.ModelAdmin):
    """Admin para tokens de ISPs"""
    list_display = ['proveedor_nombre', 'activo', 'archivos_subidos', 'ultima_subida', 'fecha_expiracion', 'copiar_url']
    list_filter = ['activo', 'fecha_creacion', 'fecha_expiracion']
    search_fields = ['proveedor_nombre', 'email_contacto']
    readonly_fields = ['token', 'fecha_creacion', 'archivos_subidos', 'ultima_subida', 'mostrar_url_completa']
    
    fieldsets = (
        ('Información del ISP', {
            'fields': ('proveedor_nombre', 'email_contacto', 'activo')
        }),
        ('Token de Acceso', {
            'fields': ('token', 'mostrar_url_completa', 'fecha_expiracion')
        }),
        ('Estadísticas', {
            'fields': ('archivos_subidos', 'ultima_subida', 'fecha_creacion')
        }),
    )
    
    def mostrar_url_completa(self, obj):
        """Muestra la URL completa para copiar"""
        if obj.token:
            url = obj.get_upload_url()
            return format_html(
                '<input type="text" value="{}" style="width: 100%; padding: 5px;" '
                'onclick="this.select(); document.execCommand(\'copy\'); '
                'alert(\'URL copiada al portapapeles\');" readonly>',
                url
            )
        return '-'
    mostrar_url_completa.short_description = 'URL de Upload (click para copiar)'
    
    def copiar_url(self, obj):
        """Botón para copiar URL"""
        if obj.token:
            return format_html(
                '<a class="button" href="javascript:void(0)" '
                'onclick="navigator.clipboard.writeText(\'{}\'); alert(\'URL copiada!\')">📋 Copiar URL</a>',
                obj.get_upload_url()
            )
        return '-'
    copiar_url.short_description = 'URL'


@admin.register(BulkQueryJob)
class BulkQueryJobAdmin(admin.ModelAdmin):
    """Admin para consultas masivas"""
    list_display = ['id', 'usuario', 'status', 'total_registros', 'progreso', 'fecha_creacion', 'descargar_resultado']
    list_filter = ['status', 'fecha_creacion']
    search_fields = ['usuario__username', 'usuario__email']
    readonly_fields = ['fecha_creacion', 'fecha_inicio', 'fecha_finalizacion', 'total_registros', 
                       'registros_procesados', 'progreso', 'archivo_entrada']
    
    fieldsets = (
        ('Información', {
            'fields': ('usuario', 'status', 'archivo_entrada')
        }),
        ('Progreso', {
            'fields': ('total_registros', 'registros_procesados', 'progreso')
        }),
        ('Resultado', {
            'fields': ('archivo_salida', 'error_mensaje')
        }),
        ('Fechas', {
            'fields': ('fecha_creacion', 'fecha_inicio', 'fecha_finalizacion')
        }),
    )
    
    def progreso(self, obj):
        """Muestra barra de progreso"""
        porcentaje = obj.progreso_porcentaje
        color = '#4CAF50' if obj.status == 'completed' else '#2196F3'
        if obj.status == 'failed':
            color = '#f44336'
        
        return format_html(
            '<div style="width: 100%; background: #ddd; border-radius: 3px;">'
            '<div style="width: {}%; background: {}; padding: 2px 0; text-align: center; '
            'color: white; border-radius: 3px;">{:.0f}%</div></div>',
            porcentaje, color, porcentaje
        )
    progreso.short_description = 'Progreso'
    
    def descargar_resultado(self, obj):
        """Botón para descargar resultado"""
        if obj.archivo_salida and obj.status == 'completed':
            return format_html(
                '<a class="button" href="{}" download>⬇️ Descargar CSV</a>',
                obj.archivo_salida.url
            )
        return '-'
    descargar_resultado.short_description = 'Resultado'
