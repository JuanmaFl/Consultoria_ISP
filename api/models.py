from django.db import models
from django.contrib.auth.models import AbstractUser


class Usuario(AbstractUser):
    """Usuario personalizado para el sistema de consultoría ISP"""
    telefono = models.CharField(max_length=20, blank=True, null=True)
    empresa = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = 'Usuario'
        verbose_name_plural = 'Usuarios'

    def __str__(self):
        return f"{self.username} - {self.get_full_name()}"
