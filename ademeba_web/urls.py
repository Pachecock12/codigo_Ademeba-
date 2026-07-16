from django.contrib import admin
from django.urls import path, include
from gestion import views
from django.conf import settings
from django.urls import re_path
from django.views.static import serve

urlpatterns = [
    path('admin/', admin.site.urls),
    path('cuentas/', include('django.contrib.auth.urls')), 
    path('registro/', views.registro_padre, name='registro'),
    
    path('', views.dashboard_entrenador, name='dashboard'),
    
    # --- RUTAS DE COMPETICIONES ---
    path('administracion/competiciones/', views.lista_temporadas, name='lista_temporadas'),
    path('administracion/competiciones/<int:temporada_id>/', views.detalle_temporada, name='detalle_temporada'),
    path('administracion/competiciones/<int:temporada_id>/editar/', views.editar_temporada, name='editar_temporada'),
    path('administracion/competiciones/<int:temporada_id>/eliminar/', views.eliminar_temporada, name='eliminar_temporada'),
    path('administracion/competiciones/<int:temporada_id>/partidos/', views.gestionar_partidos, name='gestionar_partidos'),
    path('administracion/competiciones/<int:temporada_id>/resultados/excel/', views.descargar_resultados_excel, name='descargar_resultados_excel'),
    path('administracion/competiciones/<int:temporada_id>/campeon/', views.declarar_campeon, name='declarar_campeon'),
    path('administracion/competiciones/<int:temporada_id>/toggle-inscripciones/', views.toggle_inscripciones, name='toggle_inscripciones'),
    
    # --- RUTAS DE ARCHIVO HISTÓRICO ---
    path('administracion/archivo/', views.archivo_index, name='archivo_index'),
    path('administracion/archivo/<int:anio>/', views.archivo_historico_anio, name='archivo_historico_anio'),
    path('administracion/archivo/torneo/<int:temporada_id>/', views.archivo_historico_detalle, name='archivo_historico_detalle'),
    
    # --- RUTAS DE EQUIPOS Y ENTRENADORES ---
    path('administracion/equipos/', views.lista_equipos, name='lista_equipos'),
    path('administracion/equipos/eliminar/<int:equipo_id>/', views.eliminar_equipo, name='eliminar_equipo'),
    
    path('administracion/entrenadores/', views.lista_entrenadores, name='lista_entrenadores'),
    path('administracion/entrenadores/<int:user_id>/reset-password/', views.resetear_password, name='resetear_password'),
    path('administracion/entrenadores/<int:user_id>/editar/', views.editar_cuenta_entrenador, name='editar_cuenta_entrenador'),
    path('administracion/entrenadores/<int:user_id>/toggle-acceso/', views.toggle_acceso_entrenador, name='toggle_acceso_entrenador'),
    
    # --- RUTAS DE SECRETARÍA / FINANZAS ---
    path('administracion/finanzas/', views.panel_finanzas, name='panel_finanzas'),
    path('administracion/finanzas/eliminar/<int:pk>/', views.eliminar_adeudo, name='eliminar_adeudo'),
    path('administracion/finanzas/cobrar/<int:pk>/', views.cobrar_efectivo, name='cobrar_efectivo'),
    path('administracion/finanzas/aprobar-voucher/<int:pk>/', views.aprobar_voucher, name='aprobar_voucher'),
    path('administracion/finanzas/rechazar-voucher/<int:pk>/', views.rechazar_voucher, name='rechazar_voucher'),
    path('administracion/finanzas/historial/', views.historial_finanzas, name='historial_finanzas'),
    path('administracion/finanzas/historial/<int:anio>/', views.historial_finanzas_anio, name='historial_finanzas_anio'),
    path('administracion/finanzas/excel/<int:anio>/', views.descargar_excel_finanzas, name='descargar_excel_finanzas'),
    
    path('administracion/disciplina/', views.panel_disciplina, name='panel_disciplina'),
    path('administracion/disciplina/eliminar/<int:pk>/', views.eliminar_sancion, name='eliminar_sancion'),
    path('disciplina/jugador/<int:jugador_id>/', views.gestion_sanciones_jugador, name='gestion_sanciones_jugador'),
    path('administracion/aprobaciones/', views.panel_aprobaciones, name='panel_aprobaciones'),
    
    path('administracion/cambios-equipo/', views.lista_cambios_equipo, name='lista_cambios_equipo'),
    path('administracion/cambios-equipo/<int:solicitud_id>/<str:accion>/', views.procesar_cambio_equipo, name='procesar_cambio_equipo'),
    
    path('administracion/configuracion/', views.panel_configuracion, name='panel_configuracion'),
    path('administracion/sistema/', views.panel_sistema, name='panel_sistema'),
    path('administracion/sistema/respaldo/', views.descargar_respaldo_bd, name='descargar_respaldo_bd'),
    path('administracion/inscripcion/<int:inscripcion_id>/validar/', views.validar_inscripcion, name='validar_inscripcion'),
    path('administracion/solicitudes-contrasena/', views.lista_solicitudes_contrasena, name='lista_solicitudes_contrasena'),
    
    # --- RUTAS GESTIÓN DE EQUIPO (ENTRENADOR/ADMIN) ---
    path('equipo/<int:equipo_id>/gestionar/', views.gestionar_equipo, name='gestionar_equipo'),
    path('equipo/<int:equipo_id>/logo/', views.cambiar_logo_equipo, name='cambiar_logo_equipo'),
    path('perfil/', views.perfil_entrenador, name='perfil_entrenador'),
    path('perfil/editar/', views.editar_perfil_entrenador, name='editar_perfil_entrenador'),
    path('equipo/mis-torneos/', views.mis_torneos_entrenador, name='mis_torneos_entrenador'),
    path('equipo/mis-adeudos/', views.mis_adeudos_entrenador, name='mis_adeudos_entrenador'),
    path('staff/<int:pk>/eliminar/', views.eliminar_staff, name='eliminar_staff'),
    path('staff/<int:pk>/editar/', views.editar_staff, name='editar_staff'),
    
    # --- RUTAS DEL TUTOR Y ENTRENADOR ---
    path('tutor/equipos/', views.equipos_tutor, name='equipos_tutor'),
    path('tutor/equipos/<int:equipo_id>/registrar/', views.registrar_jugador_equipo, name='registrar_jugador_equipo'),
    path('entrenador/nuevos-jugadores/', views.nuevos_jugadores_entrenador, name='nuevos_jugadores_entrenador'),
    
    path('jugador/<int:jugador_id>/solicitar-cambio/', views.solicitar_cambio_equipo, name='solicitar_cambio_equipo'),
    path('jugador/<int:jugador_id>/baja/', views.dar_de_baja_jugador, name='dar_de_baja_jugador'),
    
    # --- RUTAS DE PAGOS ---
    path('adeudo/<int:adeudo_id>/pagar/', views.subir_voucher_adeudo, name='subir_voucher_adeudo'),
    path('sancion/<int:sancion_id>/pagar/', views.pagar_multa, name='pagar_multa'),
    
    # --- RUTAS DE ROSTERS ---
    path('roster/<int:temporada_id>/<int:equipo_id>/', views.gestionar_roster, name='gestionar_roster'),
    path('roster/<int:temporada_id>/<int:equipo_id>/cedula/pdf/', views.generar_cedula_pdf, name='generar_cedula_pdf'),
    path('roster/<int:temporada_id>/<int:equipo_id>/excel/', views.descargar_roster_excel, name='descargar_roster_excel'),
    
    # --- RUTAS DE JUGADORES ---
    path('jugador/editar/<int:pk>/', views.editar_jugador_tutor, name='editar_jugador_tutor'), 
    path('jugador/<int:pk>/perfil/', views.perfil_jugador, name='perfil_jugador'),
    path('jugador/<int:pk>/eliminar/', views.eliminar_jugador, name='eliminar_jugador'),
    path('mi-familia/jugadores/', views.mis_jugadores, name='mis_jugadores'),
    
    # --- MÓDULO DE BAJAS ---
    path('jugadores/bajas/', views.lista_jugadores_baja, name='jugadores_baja'),
    path('jugadores/reactivar/<int:pk>/', views.reactivar_jugador, name='reactivar_jugador'),
    
    # --- RUTAS DE VALIDACIÓN ---
    path('cuentas/solicitar-cambio-contrasena/', views.solicitar_cambio_contrasena, name='solicitar_cambio_contrasena'),
    path('cuentas/verificar-solicitud/', views.verificar_solicitud_contrasena, name='verificar_solicitud_contrasena'),
    path('cuentas/cambiar-contrasena/', views.cambiar_contrasena, name='cambiar_contrasena'),
    
    path('administracion/aprobar/<int:pk>/', views.aprobar_jugador, name='aprobar_jugador'),
    path('administracion/rechazar/<int:pk>/', views.rechazar_jugador, name='rechazar_jugador'),
    path('administracion/rechazar-motivo/<int:pk>/', views.rechazar_jugador_con_motivo, name='rechazar_jugador_con_motivo'),
    
    # --- RUTAS DE EXPORTACIÓN Y VISTA PÚBLICA ---
    path('jugador/<int:pk>/credencial/pdf/', views.generar_credencial_pdf, name='credencial_jugador_pdf'),
    path('jugador/<int:pk>/credencial/', views.credencial_jugador, name='credencial_jugador'),
    path('valida/jugador/<int:pk>/', views.validar_jugador_qr, name='validar_jugador_qr'),

    # --- MÓDULO DE REEMBOLSOS ---
    path('jugador/<int:jugador_id>/reembolso/', views.solicitar_reembolso, name='solicitar_reembolso'),
    path('administracion/reembolsos/', views.panel_reembolsos, name='panel_reembolsos'),
    path('administracion/reembolsos/<int:pk>/procesar/', views.procesar_reembolso, name='procesar_reembolso'),
]

# Servir archivos multimedia (funciona incluso con DEBUG=False en Railway)
urlpatterns += [re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT})]