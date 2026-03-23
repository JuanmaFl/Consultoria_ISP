from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.gis.admin import GISModelAdmin
from django.utils.html import format_html
from django.urls import reverse
from .models import Usuario, CoberturaISP


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
    """Admin para coberturas ISP"""
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

    def eliminar_archivo(self, obj):
        if obj.archivo_origen:
            return format_html(
                '<a class="button" href="{}">Eliminar</a>',
                reverse('admin:api_coberturaisp_delete', args=[obj.pk])
            )
        return '-'
    eliminar_archivo.short_description = 'Acciones'

    def eliminar_archivos_kmz(self, request, queryset):
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
        if not change:
            obj.usuario_subida = request.user
        super().save_model(request, obj, form, change)