from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Usuario


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
