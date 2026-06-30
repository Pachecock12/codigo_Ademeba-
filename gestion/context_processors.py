from .models import Temporada, Equipo, SolicitudCambioContrasena

def archivo_historico_sidebar(request):
    anios = Temporada.objects.filter(campeon__isnull=False).dates('fecha_inicio', 'year').reverse()
    return {
        'anios_historicos_sidebar': [fecha.year for fecha in anios]
    }

def equipos_sidebar(request):
    if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
        equipos = Equipo.objects.all().order_by('club', 'nombre')
        return {'lista_equipos_sidebar': equipos}
    return {}

def solicitudes_contrasena_sidebar(request):
    if request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser):
        pendientes = SolicitudCambioContrasena.objects.filter(estado='PENDIENTE').count()
        return {
            'solicitudes_contrasena_pendientes': pendientes,
        }
    return {}