from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin
from .models import Equipo, Jugador, Sancion, Adeudo, ConfiguracionSistema, SolicitudCambioContrasena

admin.site.unregister(User)
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active', 'date_joined']
    list_filter = ['is_staff', 'is_superuser', 'is_active', 'groups']

@admin.register(Equipo)
class EquipoAdmin(admin.ModelAdmin):
    list_display = ['club', 'nombre', 'entrenador', 'rama', 'max_jugadores']
    list_filter = ['rama', 'club']
    search_fields = ['club', 'nombre']
    readonly_fields = ['logo']

@admin.register(Jugador)
class JugadorAdmin(admin.ModelAdmin):
    list_display = ['nombres', 'apellido_paterno', 'apellido_materno', 'curp', 'equipo', 'estado_validacion', 'activo']
    list_filter = ['estado_validacion', 'activo', 'region', 'rama']
    search_fields = ['nombres', 'apellido_paterno', 'curp', 'numero_afiliacion']
    readonly_fields = ['numero_afiliacion', 'codigo_qr']
    fieldsets = [
        ('Datos Personales', {'fields': ['nombres', 'apellido_paterno', 'apellido_materno', 'curp', 'fecha_nacimiento', 'rama']}),
        ('Contacto', {'fields': ['region', 'municipio_vive', 'telefono_credencial']}),
        ('Deportivos', {'fields': ['numero_camiseta', 'posicion', 'tipo_sangre', 'equipo']}),
        ('Documentos', {'fields': ['foto_perfil', 'archivo_curp', 'archivo_identificacion', 'acta_nacimiento', 'credencial_escolar', 'archivo_afiliacion', 'archivo_pago']}),
        ('Validación', {'fields': ['estado_validacion', 'validado', 'motivo_rechazo', 'intentos_registro']}),
        ('Afiliación', {'fields': ['numero_afiliacion', 'codigo_qr']}),
    ]

@admin.register(Sancion)
class SancionAdmin(admin.ModelAdmin):
    list_display = ['jugador', 'tipo', 'fecha_sancion', 'activa', 'juegos_suspension', 'monto_multa']
    list_filter = ['tipo', 'activa']
    search_fields = ['jugador__nombres', 'jugador__apellido_paterno', 'motivo']

@admin.register(Adeudo)
class AdeudoAdmin(admin.ModelAdmin):
    list_display = ['concepto', 'equipo', 'monto', 'estado', 'pagado', 'tipo_adeudo', 'fecha_creacion']
    list_filter = ['estado', 'tipo_adeudo', 'pagado']
    search_fields = ['concepto', 'equipo__club', 'jugador__nombres']
    readonly_fields = ['fecha_creacion', 'fecha_pago']

@admin.register(ConfiguracionSistema)
class ConfiguracionSistemaAdmin(admin.ModelAdmin):
    exclude = []

    def has_add_permission(self, request):
        return not ConfiguracionSistema.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

class SolicitudCambioContrasenaAdmin(admin.ModelAdmin):
    list_display = ['usuario', 'estado', 'fecha_solicitud']
    list_filter = ['estado']
    search_fields = ['usuario__username', 'usuario__email']
    readonly_fields = ['fecha_solicitud', 'contrasena_temporal']
admin.site.register(SolicitudCambioContrasena, SolicitudCambioContrasenaAdmin)