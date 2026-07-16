import json
import logging
from django.shortcuts import render, redirect, get_object_or_404

logger = logging.getLogger(__name__)
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.models import User
from django.db.models import Q, Sum, Count
from .forms import JugadorForm, MiembroStaffForm, HijoForm, RegistroTutorForm, EquipoForm, RegistroEntrenadorForm, AdeudoForm, TemporadaForm, TemporadaEditForm, RosterForm, PartidoForm, ResultadoForm, SancionForm, SolicitudCambioForm, VoucherForm, ConfiguracionSistemaForm, SolicitudCambioContrasenaForm, EntrenadorPerfilForm, ResetPasswordForm, EditarCuentaEntrenadorForm
from .models import Jugador, Equipo, MiembroStaff, HistorialEquipo, PerfilTutor, PerfilEntrenador, Adeudo, Temporada, InscripcionTorneo, Partido, Sancion, SolicitudCambioEquipo, ConfiguracionSistema, SolicitudCambioContrasena, Reembolso
from datetime import date
from django.http import HttpResponse
from django.conf import settings
import os
import csv
from django.core.management import call_command
import io
from django.utils import timezone
from django.core.paginator import Paginator
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor

# =========================================================
# PERMISOS Y UTILIDADES
# =========================================================

# SOLUCIÓN HUECO 5: Blindaje de Permisos. Ya no dependemos ciegamente de que el grupo exista.
def secretaria_required(function=None, redirect_url='dashboard'):
    def check_perms(u):
        if not u.is_authenticated: return False
        if u.is_superuser or u.is_staff: return True
        return u.groups.filter(name='Secretarias').exists()

    actual_decorator = user_passes_test(check_perms, login_url=redirect_url)
    if function: return actual_decorator(function)
    return actual_decorator

def admin_o_secre_check(u):
    return u.is_superuser or u.is_staff or u.groups.filter(name='Secretarias').exists()

# =========================================================
# ACCESO Y DASHBOARDS
# =========================================================
def registro_padre(peticion):
    if peticion.method == 'POST':
        form = RegistroTutorForm(peticion.POST)
        if form.is_valid():
            usuario = form.save()
            PerfilTutor.objects.create(usuario=usuario)
            messages.success(peticion, 'Cuenta creada exitosamente. Ahora puedes iniciar sesión.')
            return redirect('login')
    else: 
        form = RegistroTutorForm()
    return render(peticion, 'registration/registro.html', {'form': form})

@login_required
def dashboard(peticion):
    usuario = peticion.user
    if not usuario.is_staff and not hasattr(usuario, 'equipo_entrenado'):
        mis_hijos = Jugador.objects.filter(tutor=usuario).select_related('equipo').prefetch_related(
            'solicitudes_cambio', 'torneos_participados__temporada',
            'equipo__torneos_jugados__temporada', 'sancion_set', 'adeudos_jugador',
        )
        equipos_ids = mis_hijos.values_list('equipo_id', flat=True).exclude(equipo_id__isnull=True)
        partidos_hijos = Partido.objects.filter(
            Q(equipo_local_id__in=equipos_ids) | Q(equipo_visitante_id__in=equipos_ids),
            jugado=False
        ).select_related('equipo_local', 'equipo_visitante').order_by('fecha_hora')[:6]
        
        mis_adeudos = Adeudo.objects.filter(jugador__in=mis_hijos, estado__in=['PENDIENTE', 'REVISION']).select_related('equipo', 'jugador')
        multas_lista = Adeudo.objects.filter(jugador__in=mis_hijos, tipo_adeudo='MULTA', pagado=False).select_related('jugador', 'sancion')
        multas_totales = sum(m.monto for m in multas_lista)

        try:
            config = ConfiguracionSistema.objects.get(pk=1)
        except ConfiguracionSistema.DoesNotExist:
            config = None
        return render(peticion, 'gestion/dashboard_tutor.html', {
            'mis_hijos': mis_hijos, 'partidos_hijos': partidos_hijos, 'mis_adeudos': mis_adeudos,
            'multas_lista': multas_lista, 'multas_totales': multas_totales, 'config': config,
        })
    else:
        return redirect('dashboard')

@login_required
def dashboard_entrenador(peticion):
    es_admin_secre = admin_o_secre_check(peticion.user)
    
    if es_admin_secre:
        pendientes = Jugador.objects.filter(estado_validacion='PENDIENTE', activo=True).count()
        registrados = Jugador.objects.filter(activo=True).count()
        activos_equipo = Jugador.objects.filter(activo=True, validado=True).exclude(equipo__isnull=True).count()
        total_equipos = Equipo.objects.count()
        
        hoy = timezone.now().date()
        torneos_activos = Temporada.objects.filter(campeon__isnull=True).select_related('campeon').order_by('-fecha_inicio')[:5]
        ultimos_jugadores = Jugador.objects.filter(activo=True).order_by('-id')[:6].select_related('equipo')
        historial_partidos = Partido.objects.filter(jugado=True).select_related('temporada', 'equipo_local', 'equipo_visitante').order_by('-fecha_hora')[:10]
        
        try:
            config = ConfiguracionSistema.objects.get(pk=1)
        except ConfiguracionSistema.DoesNotExist:
            config = None
        return render(peticion, 'gestion/dashboard_entrenador.html', {
            'pendientes_globales': pendientes, 'total_registrados': registrados,
            'total_activos_en_equipo': activos_equipo, 'total_equipos': total_equipos,
            'torneos_activos': torneos_activos, 'ultimos_jugadores': ultimos_jugadores,
            'historial_partidos': historial_partidos, 'config': config,
            'es_admin_secre': es_admin_secre,
        })
        
    elif hasattr(peticion.user, 'equipo_entrenado'):
        equipo_del_entrenador = peticion.user.equipo_entrenado
        
        jugadores_pendientes = Jugador.objects.filter(equipo=equipo_del_entrenador, estado_validacion='PENDIENTE', activo=True).select_related('equipo')
        adeudos_pendientes = Adeudo.objects.filter(equipo=equipo_del_entrenador, estado__in=['PENDIENTE', 'REVISION']).select_related('equipo', 'jugador')
        torneos_activos = InscripcionTorneo.objects.filter(equipo=equipo_del_entrenador).count()
        
        proximos_partidos = Partido.objects.filter(
            Q(equipo_local=equipo_del_entrenador) | Q(equipo_visitante=equipo_del_entrenador), 
            jugado=False
        ).select_related('equipo_local', 'equipo_visitante', 'temporada').order_by('fecha_hora')[:4]
        
        ultimos_resultados = Partido.objects.filter(
            Q(equipo_local=equipo_del_entrenador) | Q(equipo_visitante=equipo_del_entrenador), 
            jugado=True
        ).select_related('equipo_local', 'equipo_visitante', 'temporada').order_by('-fecha_hora')[:4]
        
        jugadores_pendientes_count = jugadores_pendientes.count()
        adeudos_pendientes_count = adeudos_pendientes.count()
        historial_partidos = Partido.objects.filter(
            Q(equipo_local=equipo_del_entrenador) | Q(equipo_visitante=equipo_del_entrenador),
            jugado=True
        ).select_related('temporada', 'equipo_local', 'equipo_visitante').order_by('-fecha_hora')[:10]

        try:
            config = ConfiguracionSistema.objects.get(pk=1)
        except ConfiguracionSistema.DoesNotExist:
            config = None
        return render(peticion, 'gestion/dashboard_entrenador.html', {
            'equipo': equipo_del_entrenador, 'equipos': [equipo_del_entrenador],
            'jugadores_pendientes_count': jugadores_pendientes_count,
            'jugadores_pendientes': jugadores_pendientes,
            'adeudos_pendientes': adeudos_pendientes, 'adeudos_pendientes_count': adeudos_pendientes_count,
            'total_torneos': torneos_activos,
            'proximos_partidos': proximos_partidos, 'ultimos_resultados': ultimos_resultados,
            'historial_partidos': historial_partidos, 'config': config,
            'es_admin_secre': es_admin_secre,
        })
    else:
        return dashboard(peticion)

@login_required
def perfil_entrenador(peticion):
    if not hasattr(peticion.user, 'equipo_entrenado'):
        messages.warning(peticion, 'No tienes un equipo asignado.')
        return redirect('dashboard')
    equipo = peticion.user.equipo_entrenado
    jugadores = Jugador.objects.filter(equipo=equipo, activo=True)
    torneos = InscripcionTorneo.objects.filter(equipo=equipo)
    perfil, _ = PerfilEntrenador.objects.get_or_create(usuario=peticion.user)
    return render(peticion, 'gestion/perfil_entrenador.html', {
        'equipo': equipo,
        'jugadores': jugadores,
        'total_jugadores': jugadores.count(),
        'total_validados': jugadores.filter(validado=True).count(),
        'total_torneos': torneos.count(),
        'torneos': torneos,
        'perfil_entrenador': perfil,
    })

@login_required
def editar_perfil_entrenador(peticion):
    if not hasattr(peticion.user, 'equipo_entrenado'):
        messages.warning(peticion, 'No tienes un equipo asignado.')
        return redirect('dashboard')
    perfil, _ = PerfilEntrenador.objects.get_or_create(usuario=peticion.user)
    if peticion.method == 'POST':
        form = EntrenadorPerfilForm(peticion.POST, peticion.FILES, instance=perfil, user=peticion.user)
        if form.is_valid():
            form.save()
            messages.success(peticion, 'Perfil actualizado correctamente.')
            return redirect('perfil_entrenador')
    else:
        form = EntrenadorPerfilForm(instance=perfil, user=peticion.user)
    return render(peticion, 'gestion/editar_perfil_entrenador.html', {
        'form': form,
    })

# =========================================================
# GESTIÓN DE NUEVOS JUGADORES
# =========================================================
@login_required
def equipos_tutor(peticion):
    if hasattr(peticion.user, 'equipo_entrenado') or peticion.user.is_staff:
        return redirect('dashboard')
    
    try:
        config = ConfiguracionSistema.objects.get(pk=1)
        hay_inscripciones = config.inscripciones_activas
    except ConfiguracionSistema.DoesNotExist:
        config = None
        hay_inscripciones = Temporada.objects.filter(
            inscripciones_abiertas=True, campeon__isnull=True
        ).exists()

    equipos = Equipo.objects.annotate(
        num_jugadores=Count('jugador', filter=Q(jugador__activo=True, jugador__validado=True))
    ).order_by('club')
    
    return render(peticion, 'gestion/equipos_tutor.html', {
        'equipos': equipos,
        'hay_inscripciones': hay_inscripciones,
        'config': config,
    })

@login_required
def registrar_jugador_equipo(peticion, equipo_id):
    equipo = get_object_or_404(Equipo, id=equipo_id)
    
    try:
        config = ConfiguracionSistema.objects.get(pk=1)
        hay_inscripciones = config.inscripciones_activas
    except ConfiguracionSistema.DoesNotExist:
        config = None
        hay_inscripciones = Temporada.objects.filter(
            inscripciones_abiertas=True, campeon__isnull=True
        ).exists()
    
    if not hay_inscripciones:
        messages.error(peticion, 'En este momento no hay inscripciones abiertas. No puedes registrar jugadores.')
        return redirect('equipos_tutor')
    
    jugadores_activos = Jugador.objects.filter(equipo=equipo, activo=True).count()
    if jugadores_activos >= equipo.max_jugadores:
        messages.error(peticion, f'El equipo {equipo.club} ya ha alcanzado su límite máximo de {equipo.max_jugadores} jugadores. No es posible registrar más jugadores en este equipo.')
        return redirect('equipos_tutor')
    
    if peticion.method == 'POST':
        form = HijoForm(peticion.POST, peticion.FILES)
        if form.is_valid():
            try:
                hijo = form.save(commit=False)
                hijo.tutor = peticion.user
                hijo.equipo = equipo 
                hijo.estado_validacion = 'PENDIENTE'
                hijo.save()
                HistorialEquipo.objects.create(jugador=hijo, equipo=equipo, motivo="Ingreso al registrarse")

                concepto_pago = f"Inscripción - {hijo.nombres} {hijo.apellido_paterno}"
                costo = config.costo_inscripcion if config and config.costo_inscripcion else 0.00
                Adeudo.objects.get_or_create(
                    tutor=peticion.user, equipo=equipo, jugador=hijo, concepto=concepto_pago,
                    defaults={'monto': costo, 'tipo_adeudo': 'INSCRIPCION', 'estado': 'PENDIENTE'}
                )

                messages.success(peticion, f'Registro enviado al equipo {equipo.club}. Se ha generado un adeudo de inscripción de ${costo:.2f}.')
                return redirect('dashboard')
            except Exception as e:
                messages.error(peticion, 'Error al guardar los archivos en el servidor. Verifica que los archivos sean válidos y que la conexión esté configurada correctamente.')
                logger.exception("Error al registrar jugador con archivos")
        else:
            for field, errores in form.errors.items():
                for error in errores:
                    messages.error(peticion, f'{field}: {error}')
    else:
        form = HijoForm()
    return render(peticion, 'gestion/registrar_jugador_equipo.html', {'form': form, 'equipo': equipo, 'jugadores_activos': jugadores_activos, 'config': config})

@login_required
def nuevos_jugadores_entrenador(peticion):
    if not hasattr(peticion.user, 'equipo_entrenado'): return redirect('dashboard')
    equipo = peticion.user.equipo_entrenado
    nuevos_jugadores = Jugador.objects.filter(equipo=equipo, activo=True, estado_validacion='PENDIENTE').select_related('tutor').order_by('-id')
    return render(peticion, 'gestion/nuevos_jugadores.html', {'equipo': equipo, 'nuevos_jugadores': nuevos_jugadores})

# =========================================================
# GESTIÓN DEL TUTOR (EDITAR Y CAMBIOS DE EQUIPO)
# =========================================================
@login_required
def editar_jugador_tutor(peticion, pk):
    hijo = get_object_or_404(Jugador, pk=pk, tutor=peticion.user)
    if hijo.estado_validacion == 'APROBADO':
        messages.error(peticion, "Este jugador ya está aprobado por la liga y sus datos no pueden editarse.")
        return redirect('dashboard')
    if hijo.intentos_registro >= 3:
        messages.error(peticion, "Has superado el límite de 3 intentos. Por favor, contacta a soporte de ADEMEBA.")
        return redirect('dashboard')

    if peticion.method == 'POST':
        form = HijoForm(peticion.POST, peticion.FILES, instance=hijo)
        if form.is_valid():
            hijo = form.save(commit=False)
            hijo.estado_validacion = 'PENDIENTE' 
            hijo.motivo_rechazo = None 
            hijo.save()
            messages.success(peticion, "Documentación actualizada y enviada a revisión nuevamente.")
            return redirect('dashboard')
    else:
        form = HijoForm(instance=hijo)
    return render(peticion, 'gestion/editar_jugador_tutor.html', {'form': form, 'hijo': hijo})

@login_required
def solicitar_cambio_equipo(peticion, jugador_id):
    jugador = get_object_or_404(Jugador, id=jugador_id, tutor=peticion.user)
    if not jugador.activo:
        messages.error(peticion, 'El jugador está inactivo, no puede solicitar cambios. Contacta a administración.')
        return redirect('dashboard')
        
    if jugador.equipo:
        en_torneo_activo = any(ins.temporada.estado_actual == 'En Curso' for ins in jugador.torneos_participados.all())
        if en_torneo_activo:
            messages.error(peticion, 'No puedes solicitar cambio de equipo. El jugador está comprometido en una liga activa.')
            return redirect('dashboard')

    if peticion.method == 'POST':
        form = SolicitudCambioForm(peticion.POST)
        if form.is_valid():
            if SolicitudCambioEquipo.objects.filter(jugador=jugador, estado='PENDIENTE').exists():
                messages.warning(peticion, 'Ya tienes una solicitud de cambio en proceso para este jugador.')
                return redirect('dashboard')
            equipo_destino = form.cleaned_data['equipo_destino']
            if jugador.equipo and equipo_destino == jugador.equipo:
                messages.error(peticion, 'No puedes solicitar un cambio a tu equipo actual.')
                return redirect('dashboard')
            solicitud = form.save(commit=False)
            solicitud.jugador = jugador
            solicitud.equipo_origen = jugador.equipo
            solicitud.save()
            messages.success(peticion, 'Tu solicitud ha sido enviada a la administración. Al aprobarse, se generará el adeudo correspondiente.')
            return redirect('dashboard')
    else:
        form = SolicitudCambioForm()
        if jugador.equipo:
            form.fields['equipo_destino'].queryset = Equipo.objects.exclude(id=jugador.equipo.id).order_by('club')
        else:
            form.fields['equipo_destino'].queryset = Equipo.objects.all().order_by('club')
    return render(peticion, 'gestion/solicitar_cambio.html', {'form': form, 'jugador': jugador})

# =========================================================
# GESTIÓN DE CLUBES Y EQUIPOS
# =========================================================
@login_required
@secretaria_required
def lista_equipos(peticion):
    form_equipo = EquipoForm()
    if peticion.method == 'POST':
        if 'btn_crear_equipo' in peticion.POST:
            form_equipo = EquipoForm(peticion.POST, peticion.FILES)
            if form_equipo.is_valid():
                form_equipo.save()
                messages.success(peticion, '¡Equipo creado exitosamente!')
                return redirect('lista_equipos')
            else:
                messages.error(peticion, 'Error al crear equipo. Verifica los campos.')
    equipos_lista = Equipo.objects.all().order_by('club', 'nombre')
    paginator = Paginator(equipos_lista, 20)
    page_number = peticion.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(peticion, 'gestion/lista_equipos.html', {'equipos': page_obj, 'form_equipo': form_equipo})

@login_required
def gestionar_equipo(peticion, equipo_id):
    equipo_actual = get_object_or_404(Equipo, id=equipo_id)
    if equipo_actual.entrenador != peticion.user and not peticion.user.is_staff: 
        return redirect('dashboard')

    formulario_edicion_equipo = EquipoForm(instance=equipo_actual)
    formulario_jugador = JugadorForm()
    formulario_staff = MiembroStaffForm()
    abrir_modal_jugador = False
    abrir_modal_staff = False
    
    if peticion.method == 'POST':
        if 'btn_editar_equipo' in peticion.POST and peticion.user.is_staff:
            formulario_edicion_equipo = EquipoForm(peticion.POST, peticion.FILES, instance=equipo_actual)
            if formulario_edicion_equipo.is_valid(): 
                formulario_edicion_equipo.save()
                messages.success(peticion, 'Datos del club actualizados.')
                return redirect('gestionar_equipo', equipo_id=equipo_actual.id)
                
        elif 'btn_staff' in peticion.POST:
            formulario_staff = MiembroStaffForm(peticion.POST, peticion.FILES)
            if formulario_staff.is_valid(): 
                nuevo_staff = formulario_staff.save(commit=False)
                nuevo_staff.equipo = equipo_actual
                nuevo_staff.save()
                messages.success(peticion, 'Miembro del cuerpo técnico agregado.')
                return redirect('gestionar_equipo', equipo_id=equipo_actual.id)
            else:
                for field, errores in formulario_staff.errors.items():
                    for error in errores:
                        messages.error(peticion, f'{field}: {error}')
                abrir_modal_staff = True
            
        elif 'btn_jugador' in peticion.POST and peticion.user.is_staff:
            formulario_jugador = JugadorForm(peticion.POST, peticion.FILES)
            if formulario_jugador.is_valid():
                nuevo_jugador = formulario_jugador.save(commit=False)
                nuevo_jugador.equipo = equipo_actual
                nuevo_jugador.estado_validacion = 'APROBADO'
                nuevo_jugador.validado = True
                nuevo_jugador.save()
                HistorialEquipo.objects.create(jugador=nuevo_jugador, equipo=equipo_actual, motivo="Captura Admin")

                try:
                    config = ConfiguracionSistema.objects.get(pk=1)
                    costo = config.costo_inscripcion if config and config.costo_inscripcion else 0.00
                except ConfiguracionSistema.DoesNotExist:
                    costo = 0.00
                Adeudo.objects.create(
                    tutor=nuevo_jugador.tutor, equipo=equipo_actual, jugador=nuevo_jugador,
                    concepto=f"Inscripción (Captura Admin) - {nuevo_jugador.nombres} {nuevo_jugador.apellido_paterno}",
                    monto=costo, tipo_adeudo='INSCRIPCION', estado='PENDIENTE'
                )
                
                messages.success(peticion, 'Jugador registrado, añadido al equipo y adeudo generado en finanzas.')
                return redirect('gestionar_equipo', equipo_id=equipo_actual.id)
            else:
                for field, errores in formulario_jugador.errors.items():
                    for error in errores:
                        messages.error(peticion, f'{field}: {error}')
                abrir_modal_jugador = True

        elif 'btn_vincular_curp' in peticion.POST:
            curp = peticion.POST.get('curp_busqueda', '').strip().upper()
            jugador = Jugador.objects.filter(curp=curp, activo=True).first()
            if jugador:
                if jugador.equipo and jugador.equipo != equipo_actual:
                    messages.warning(peticion, f'{jugador.nombres} {jugador.apellido_paterno} ya pertenece a {jugador.equipo.club}.')
                else:
                    jugador.equipo = equipo_actual
                    jugador.estado_validacion = 'PENDIENTE'
                    jugador.save()
                    HistorialEquipo.objects.create(jugador=jugador, equipo=equipo_actual, motivo="Vinculado por CURP")
                    messages.success(peticion, f'{jugador.nombres} {jugador.apellido_paterno} vinculado a {equipo_actual.club}.')
            else:
                messages.error(peticion, 'No se encontró ningún jugador activo con esa CURP.')
            return redirect('gestionar_equipo', equipo_id=equipo_actual.id)

    jugadores_varonil = Jugador.objects.filter(equipo=equipo_actual, activo=True, rama='Varonil').prefetch_related('torneos_participados__temporada', 'historial_equipos')
    jugadores_femenil = Jugador.objects.filter(equipo=equipo_actual, activo=True, rama='Femenil').prefetch_related('torneos_participados__temporada', 'historial_equipos')
    miembros_staff = equipo_actual.miembros_staff.all()

    return render(peticion, 'gestion/gestionar_equipo.html', {
        'equipo': equipo_actual, 'form': formulario_jugador, 'form_staff': formulario_staff, 
        'form_edicion_equipo': formulario_edicion_equipo, 'jugadores_varonil': jugadores_varonil,
        'jugadores_femenil': jugadores_femenil, 'staff': miembros_staff, 
        'abrir_modal': abrir_modal_jugador, 'abrir_modal_staff': abrir_modal_staff,
        'es_admin_secre': admin_o_secre_check(peticion.user),
    })

@login_required
def cambiar_logo_equipo(peticion, equipo_id):
    equipo = get_object_or_404(Equipo, id=equipo_id)
    if peticion.user != equipo.entrenador and not peticion.user.is_staff:
        return redirect('dashboard')
    if peticion.method == 'POST':
        form = EquipoForm(peticion.POST, peticion.FILES, instance=equipo)
        if form.is_valid():
            form.save(commit=False)
            equipo.logo = form.cleaned_data['logo']
            equipo.save()
        return redirect('gestionar_equipo', equipo_id=equipo_id)
    return redirect('gestionar_equipo', equipo_id=equipo_id)

@login_required
def eliminar_staff(peticion, pk):
    if peticion.method != 'POST':
        return redirect('dashboard')
    miembro_staff = get_object_or_404(MiembroStaff, pk=pk)
    if miembro_staff.equipo.entrenador == peticion.user or peticion.user.is_staff: 
        equipo_id = miembro_staff.equipo.id
        miembro_staff.delete()
        return redirect('gestionar_equipo', equipo_id=equipo_id)
    return redirect('dashboard')

@login_required
def editar_staff(peticion, pk):
    miembro_staff = get_object_or_404(MiembroStaff, pk=pk)
    if miembro_staff.equipo.entrenador != peticion.user and not peticion.user.is_staff:
        messages.error(peticion, 'No tienes permiso para editar este miembro.')
        return redirect('dashboard')
    if peticion.method == 'POST':
        form = MiembroStaffForm(peticion.POST, peticion.FILES, instance=miembro_staff)
        if form.is_valid():
            form.save()
            messages.success(peticion, 'Datos del cuerpo técnico actualizados correctamente.')
        else:
            messages.error(peticion, 'Error al actualizar. Verifica los campos.')
        return redirect('gestionar_equipo', equipo_id=miembro_staff.equipo.id)
    return redirect('gestionar_equipo', equipo_id=miembro_staff.equipo.id)

@login_required
@secretaria_required
def eliminar_equipo(peticion, equipo_id):
    if peticion.method != 'POST':
        return redirect('lista_equipos')
    equipo = get_object_or_404(Equipo, id=equipo_id)
    nombre_club = equipo.club
    equipo.delete()
    messages.success(peticion, f'El equipo "{nombre_club}" ha sido eliminado permanentemente del sistema.')
    return redirect('lista_equipos')

# =========================================================
# GESTIÓN DE COMPETICIONES E INSCRIPCIONES
# =========================================================
@login_required
@secretaria_required
def lista_temporadas(peticion):
    form_temporada = TemporadaForm()
    if peticion.method == 'POST':
        if 'btn_crear_temporada' in peticion.POST:
            form_temporada = TemporadaForm(peticion.POST)
            if form_temporada.is_valid():
                form_temporada.save()
                messages.success(peticion, '¡Temporada creada exitosamente!')
                return redirect('lista_temporadas')
        
    hoy = timezone.now().date()
    temporadas_activas = Temporada.objects.filter(campeon__isnull=True).annotate(inscritos=Count('inscripciones')).order_by('-fecha_inicio')
    return render(peticion, 'gestion/lista_temporadas.html', {'temporadas': temporadas_activas, 'form_temporada': form_temporada})

@login_required
@secretaria_required
def editar_temporada(peticion, temporada_id):
    temporada = get_object_or_404(Temporada, id=temporada_id)
    if peticion.method == 'POST':
        form = TemporadaEditForm(peticion.POST, instance=temporada)
        if form.is_valid():
            form.save()
            messages.success(peticion, '¡Datos del torneo actualizados correctamente!')
            return redirect('lista_temporadas')
    else:
        form = TemporadaEditForm(instance=temporada)
    return render(peticion, 'gestion/editar_temporada.html', {'form': form, 'temporada': temporada})

@login_required
@secretaria_required
def eliminar_temporada(peticion, temporada_id):
    if peticion.method != 'POST':
        return redirect('lista_temporadas')
    temporada = get_object_or_404(Temporada, id=temporada_id)
    nombre_torneo = temporada.nombre
    temporada.delete()
    messages.success(peticion, f'El torneo "{nombre_torneo}" ha sido eliminado.')
    return redirect('lista_temporadas')

@login_required
@secretaria_required
def toggle_inscripciones(peticion, temporada_id):
    temporada = get_object_or_404(Temporada, id=temporada_id)
    if temporada.campeon:
        messages.error(peticion, 'No puedes cambiar inscripciones de un torneo finalizado.')
        return redirect('lista_temporadas')
    if peticion.method == 'POST':
        temporada.inscripciones_abiertas = not temporada.inscripciones_abiertas
        temporada.save()
        estado = "ABIERTAS" if temporada.inscripciones_abiertas else "CERRADAS"
        messages.success(peticion, f'Las inscripciones para "{temporada.nombre}" han sido {estado}.')
    return redirect('detalle_temporada', temporada_id=temporada.id)

@login_required
@secretaria_required
def detalle_temporada(peticion, temporada_id):
    temporada_actual = get_object_or_404(Temporada, id=temporada_id)
    
    # SOLUCIÓN HUECO 3: Consulta N+1 usando prefetch_related para no colapsar la BBDD
    inscripciones_base = temporada_actual.inscripciones.select_related('equipo', 'equipo__entrenador').prefetch_related('jugadores').order_by('equipo__club')
    
    inscripciones_con_edades = []
    anio_torneo = temporada_actual.fecha_inicio.year if temporada_actual.fecha_inicio else date.today().year
    
    for inscripcion in inscripciones_base:
        jugadores_calculados = []
        for jugador in inscripcion.jugadores.all():
            edad = "N/A"
            if jugador.fecha_nacimiento:
                edad = anio_torneo - jugador.fecha_nacimiento.year
            jugadores_calculados.append({'obj': jugador, 'edad_calculada': edad})
            
        inscripciones_con_edades.append({
            'inscripcion_id': inscripcion.id,  
            'validada': inscripcion.validada,  
            'equipo': inscripcion.equipo,
            'jugadores_info': jugadores_calculados,
            'total_jugadores': len(inscripcion.jugadores.all())
        })
        
    return render(peticion, 'gestion/detalle_temporada.html', {
        'temporada': temporada_actual,
        'inscripciones_detalladas': inscripciones_con_edades,
        'inscripciones': inscripciones_base
    })

@login_required
@secretaria_required
def declarar_campeon(peticion, temporada_id):
    temporada = get_object_or_404(Temporada, id=temporada_id)
    
    # SOLUCIÓN HUECO 2: Validar que todos los partidos estén jugados
    total_partidos = temporada.partidos.count()
    jugados = temporada.partidos.filter(jugado=True).count()
    
    if peticion.method == 'POST':
        if total_partidos == 0 or jugados < total_partidos:
            messages.error(peticion, '⚠️ Cierre Bloqueado: No puedes declarar un campeón hasta que todos los partidos de la temporada estén marcados como jugados.')
            return redirect('lista_temporadas')
            
        equipo_id = peticion.POST.get('equipo_campeon')
        if equipo_id:
            equipo = get_object_or_404(Equipo, id=equipo_id)
            if not InscripcionTorneo.objects.filter(temporada=temporada, equipo=equipo).exists():
                messages.error(peticion, 'El equipo seleccionado no participó en este torneo.')
                return redirect('lista_temporadas')
            temporada.campeon = equipo
            temporada.save()
            messages.success(peticion, f'🏆 ¡El equipo {equipo.club} ha sido declarado CAMPEÓN! El torneo ha pasado al archivo histórico.')
            
    return redirect('lista_temporadas')

@login_required
def gestionar_roster(peticion, temporada_id, equipo_id):
    temporada_actual = get_object_or_404(Temporada, id=temporada_id)
    equipo_actual = get_object_or_404(Equipo, id=equipo_id)
    
    if equipo_actual.entrenador != peticion.user and not peticion.user.is_staff:
        messages.error(peticion, 'Acceso denegado a este equipo.')
        return redirect('dashboard')

    inscripcion = InscripcionTorneo.objects.filter(temporada=temporada_actual, equipo=equipo_actual).first()

    if peticion.method == 'POST':
        if temporada_actual.estado_actual == 'Inscripciones':
            form_roster = RosterForm(peticion.POST, instance=inscripcion, equipo=equipo_actual, temporada=temporada_actual)
            if form_roster.is_valid():
                # SOLUCIÓN HUECO 4: Flexibilidad traída desde la BBDD
                minimo = temporada_actual.min_jugadores_roster
                maximo = temporada_actual.max_jugadores_roster
                
                num_seleccionados = form_roster.cleaned_data['jugadores'].count()
                
                if num_seleccionados < minimo:
                    messages.error(peticion, f'¡Rechazado! Necesitas un mínimo de {minimo} jugadores.')
                elif num_seleccionados > maximo:
                    messages.error(peticion, f'¡Rechazado! Has excedido el máximo de {maximo} jugadores.')
                else:
                    es_nueva = inscripcion is None 
                    nueva_inscripcion = form_roster.save(commit=False)
                    nueva_inscripcion.temporada = temporada_actual
                    nueva_inscripcion.equipo = equipo_actual
                    
                    if es_nueva: nueva_inscripcion.validada = False 
                        
                    nueva_inscripcion.save()
                    form_roster.save_m2m() 
                    
                    concepto_adeudo = f"Inscripción a Torneo: {temporada_actual.nombre}"
                    Adeudo.objects.get_or_create(
                        equipo=equipo_actual, concepto=concepto_adeudo, temporada=temporada_actual,
                        defaults={'monto': temporada_actual.costo_inscripcion, 'tipo_adeudo': 'INSCRIPCION', 'estado': 'PENDIENTE'}
                    )
                    
                    messages.success(peticion, f'Roster actualizado en {temporada_actual.nombre}.')
                    if peticion.user.is_staff: return redirect('detalle_temporada', temporada_id=temporada_actual.id)
                    else: return redirect('mis_torneos_entrenador')
        else:
            messages.error(peticion, 'Las inscripciones están cerradas.')
            return redirect('dashboard')
    else:
        form_roster = RosterForm(instance=inscripcion, equipo=equipo_actual, temporada=temporada_actual)

    jugadores_seleccionados = inscripcion.jugadores.all() if inscripcion else []
    return render(peticion, 'gestion/gestionar_roster.html', {
        'temporada': temporada_actual, 'equipo': equipo_actual, 'form_roster': form_roster,
        'jugadores_seleccionados': jugadores_seleccionados, 'inscripcion': inscripcion
    })

@login_required
def mis_torneos_entrenador(peticion):
    if peticion.user.is_staff or peticion.user.is_superuser: return redirect('lista_temporadas')
    if not hasattr(peticion.user, 'equipo_entrenado'):
        messages.error(peticion, 'No tienes un equipo asignado para ver torneos.')
        return redirect('dashboard')
    
    equipo = peticion.user.equipo_entrenado
    todas_inscripciones = InscripcionTorneo.objects.filter(equipo=equipo).select_related('temporada__campeon')
    
    inscripciones_activas = []
    inscripciones_pasadas = []
    for ins in todas_inscripciones:
        if ins.temporada.estado_actual in ['Inscripciones', 'En Curso']: inscripciones_activas.append(ins)
        else: inscripciones_pasadas.append(ins)
            
    torneos_inscritos_ids = todas_inscripciones.values_list('temporada_id', flat=True)
    todas_temporadas = Temporada.objects.all().select_related('campeon').order_by('fecha_inicio')
    torneos_disponibles = [t for t in todas_temporadas if t.estado_actual in ['Inscripciones', 'En Curso'] and t.id not in torneos_inscritos_ids]
    
    return render(peticion, 'gestion/mis_torneos.html', {
        'equipo': equipo, 'inscripciones_activas': inscripciones_activas, 
        'inscripciones_pasadas': inscripciones_pasadas, 'torneos_disponibles': torneos_disponibles
    })

@login_required
def mis_adeudos_entrenador(peticion):
    if not hasattr(peticion.user, 'equipo_entrenado'):
        messages.error(peticion, 'No tienes equipo asignado.')
        return redirect('dashboard')
        
    equipo = peticion.user.equipo_entrenado
    adeudos_pendientes = Adeudo.objects.filter(equipo=equipo, estado__in=['PENDIENTE', 'REVISION']).order_by('-fecha_creacion')
    adeudos_pagados = Adeudo.objects.filter(equipo=equipo, estado='PAGADO').order_by('-fecha_pago')[:15]
    total_pendiente = sum([a.monto for a in adeudos_pendientes if a.estado == 'PENDIENTE'])

    try:
        config = ConfiguracionSistema.objects.get(pk=1)
    except ConfiguracionSistema.DoesNotExist:
        config = None
    return render(peticion, 'gestion/mis_adeudos_entrenador.html', {
        'equipo': equipo, 'adeudos_pendientes': adeudos_pendientes,
        'adeudos_pagados': adeudos_pagados, 'total_pendiente': total_pendiente, 'config': config,
    })

# =========================================================
# GESTIÓN DE ENTRENADORES Y STAFF
# =========================================================
@login_required
@secretaria_required
def lista_entrenadores(peticion):
    form_entrenador = RegistroEntrenadorForm()
    if peticion.method == 'POST':
        if 'btn_crear_entrenador' in peticion.POST:
            logger.info(f"POST data keys: {list(peticion.POST.keys())}")
            form_entrenador = RegistroEntrenadorForm(peticion.POST)
            if form_entrenador.is_valid():
                form_entrenador.save()
                logger.info("Entrenador creado exitosamente")
                messages.success(peticion, '¡Cuenta de entrenador creada exitosamente!')
                return redirect('lista_entrenadores')
            else:
                logger.warning(f"Form errors: {form_entrenador.errors}")
                for field, errores in form_entrenador.errors.items():
                    for error in errores:
                        if field == '__all__':
                            messages.error(peticion, f'{error}')
                        else:
                            label = form_entrenador.fields[field].label or field
                            messages.error(peticion, f'{label}: {error}')
        else:
            logger.warning("btn_crear_entrenador NOT in POST data")
        
    entrenadores_lista = User.objects.filter(is_staff=False, perfil__isnull=True).order_by('first_name', 'username')
    paginator = Paginator(entrenadores_lista, 20)
    page_number = peticion.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(peticion, 'gestion/lista_entrenadores.html', {'entrenadores': page_obj, 'form_entrenador': form_entrenador})

@login_required
@secretaria_required
def editar_cuenta_entrenador(peticion, user_id):
    usuario = get_object_or_404(User, id=user_id)
    if peticion.method == 'POST':
        form = EditarCuentaEntrenadorForm(peticion.POST)
        if form.is_valid():
            usuario.first_name = form.cleaned_data['first_name']
            usuario.last_name = form.cleaned_data['last_name']
            usuario.email = form.cleaned_data['email']
            usuario.save()
            messages.success(peticion, f'Datos de {usuario.username} actualizados correctamente.')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(peticion, f'{field}: {error}')
    return redirect('lista_entrenadores')

@login_required
@secretaria_required
def toggle_acceso_entrenador(peticion, user_id):
    if peticion.method != 'POST':
        return redirect('lista_entrenadores')
    usuario = get_object_or_404(User, id=user_id)
    if usuario == peticion.user:
        messages.error(peticion, 'No puedes suspender tu propia cuenta de acceso.')
        return redirect('lista_entrenadores')
    usuario.is_active = not usuario.is_active
    usuario.save()
    estado = "REACTIVADO" if usuario.is_active else "SUSPENDIDO"
    messages.info(peticion, f'El acceso para el usuario {usuario.username} ha sido {estado}.')
    return redirect('lista_entrenadores')

@login_required
@secretaria_required
def resetear_password(peticion, user_id):
    usuario = get_object_or_404(User, id=user_id)
    if peticion.method == 'POST':
        form = ResetPasswordForm(peticion.POST)
        if form.is_valid():
            usuario.set_password(form.cleaned_data['nueva_password'])
            usuario.save()
            messages.success(peticion, f'La contraseña de {usuario.username} se actualizó correctamente.')
        else:
            for error in form.errors.get('nueva_password', []):
                messages.error(peticion, error)
    return redirect('lista_entrenadores')

# =========================================================
# PANEL DE SISTEMA Y RESPALDOS
# =========================================================
@login_required
@user_passes_test(lambda u: u.is_superuser)
def panel_sistema(peticion):
        
    stats = {
        'total_jugadores': Jugador.objects.count(), 'jugadores_activos': Jugador.objects.filter(activo=True).count(),
        'total_equipos': Equipo.objects.count(), 'total_usuarios': User.objects.count(), 'total_torneos': Temporada.objects.count(),
    }
    return render(peticion, 'gestion/panel_sistema.html', {'stats': stats})

@login_required
def descargar_respaldo_bd(peticion):
    if not peticion.user.is_superuser: return redirect('dashboard')
    salida = io.StringIO()
    call_command('dumpdata', exclude=['contenttypes', 'auth.Permission', 'sessions'], format='json', indent=2, stdout=salida)
    response = HttpResponse(salida.getvalue(), content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="Respaldo_ADEMEBA_{date.today()}.json"'
    return response

# =========================================================
# FINANZAS Y DISCIPLINA
# =========================================================
@login_required
@user_passes_test(admin_o_secre_check)
def panel_finanzas(peticion):
    adeudos_pendientes = Adeudo.objects.filter(estado__in=['PENDIENTE', 'REVISION']).select_related('equipo', 'jugador').order_by('-fecha_creacion')
    adeudos_pagados = Adeudo.objects.filter(estado='PAGADO').select_related('equipo', 'jugador').order_by('-fecha_pago')[:30]

    if peticion.method == 'POST':
        form_adeudo = AdeudoForm(peticion.POST)
        if form_adeudo.is_valid():
            nuevo_adeudo = form_adeudo.save(commit=False)
            nuevo_adeudo.estado = 'PENDIENTE'
            nuevo_adeudo.save()
            messages.success(peticion, 'Cargo generado correctamente.')
            return redirect('panel_finanzas')
    else:
        form_adeudo = AdeudoForm()

    try:
        config = ConfiguracionSistema.objects.get(pk=1)
    except ConfiguracionSistema.DoesNotExist:
        config = None
    return render(peticion, 'gestion/finanzas.html', {
        'adeudos_pendientes': adeudos_pendientes, 'adeudos_pagados': adeudos_pagados, 'form_adeudo': form_adeudo,
        'config': config,
    })

@login_required
@user_passes_test(admin_o_secre_check)
def eliminar_adeudo(peticion, pk):
    if peticion.method != 'POST':
        return redirect('panel_finanzas')
    adeudo = get_object_or_404(Adeudo, pk=pk)
    adeudo.delete()
    messages.success(peticion, 'El adeudo ha sido anulado del sistema.')
    return redirect('panel_finanzas')

@login_required
@user_passes_test(admin_o_secre_check)
def cobrar_efectivo(peticion, pk):
    if peticion.method != 'POST':
        return redirect('panel_finanzas')
    adeudo = get_object_or_404(Adeudo, pk=pk)
    adeudo.estado = 'PAGADO'
    adeudo.fecha_pago = timezone.now()
    adeudo.save() 
    
    if adeudo.temporada and adeudo.equipo:
        InscripcionTorneo.objects.filter(equipo=adeudo.equipo, temporada=adeudo.temporada).update(validada=True)
            
    messages.success(peticion, f'Adeudo saldado. Se ha habilitado al equipo para jugar oficialmente.')
    return redirect('panel_finanzas')

@login_required
@user_passes_test(admin_o_secre_check)
def aprobar_voucher(peticion, pk):
    if peticion.method != 'POST':
        return redirect('panel_finanzas')
    adeudo = get_object_or_404(Adeudo, pk=pk)
    adeudo.estado = 'PAGADO'
    adeudo.fecha_pago = timezone.now()
    adeudo.save()
    
    if adeudo.temporada and adeudo.equipo:
        InscripcionTorneo.objects.filter(equipo=adeudo.equipo, temporada=adeudo.temporada).update(validada=True)
            
    messages.success(peticion, 'Voucher aprobado exitosamente. El pago ha sido registrado.')
    return redirect('panel_finanzas')

@login_required
@user_passes_test(admin_o_secre_check)
def rechazar_voucher(peticion, pk):
    adeudo = get_object_or_404(Adeudo, pk=pk)
    if adeudo.estado != 'REVISION':
        messages.error(peticion, 'Este adeudo no está en revisión.')
        return redirect('panel_finanzas')
    adeudo.estado = 'PENDIENTE'
    adeudo.voucher_comprobante = None
    adeudo.save()
    messages.warning(peticion, f'Voucher rechazado. El adeudo "{adeudo.concepto}" ha vuelto a estado pendiente.')
    return redirect('panel_finanzas')

@login_required
@user_passes_test(admin_o_secre_check)
def historial_finanzas(peticion):
    anios_db = Adeudo.objects.dates('fecha_creacion', 'year', order='DESC')
    anios_data = []
    for fecha in anios_db:
        anio = fecha.year
        total = Adeudo.objects.filter(fecha_creacion__year=anio, estado='PAGADO').aggregate(Sum('monto'))['monto__sum'] or 0
        anios_data.append({'year': anio, 'total_ingresado': total})
    return render(peticion, 'gestion/historial_finanzas_index.html', {'anios': anios_data})

@login_required
@user_passes_test(admin_o_secre_check)
def historial_finanzas_anio(peticion, anio):
    base_qs = Adeudo.objects.filter(fecha_creacion__year=anio)
    
    total_cobrado = base_qs.filter(estado='PAGADO').aggregate(Sum('monto'))['monto__sum'] or 0
    total_pendiente = base_qs.filter(estado__in=['PENDIENTE', 'REVISION']).aggregate(Sum('monto'))['monto__sum'] or 0
    
    adeudos_del_anio = base_qs.select_related('equipo', 'jugador').order_by('-fecha_creacion')
    estado_filtro = peticion.GET.get('estado')
    if estado_filtro: adeudos_del_anio = adeudos_del_anio.filter(estado=estado_filtro)

    paginator = Paginator(adeudos_del_anio, 15) 
    page_number = peticion.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(peticion, 'gestion/historial_finanzas_anio.html', {
        'anio': anio, 'adeudos': page_obj, 'total_cobrado': total_cobrado, 'total_pendiente': total_pendiente
    })

@login_required
@user_passes_test(admin_o_secre_check)
def descargar_excel_finanzas(peticion, anio):
    adeudos = Adeudo.objects.filter(fecha_creacion__year=anio).select_related('equipo', 'jugador').order_by('-fecha_creacion')
    estado_filtro = peticion.GET.get('estado')
    if estado_filtro: adeudos = adeudos.filter(estado=estado_filtro)

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="Finanzas_ADEMEBA_{anio}.csv"'
    response.write('\ufeff'.encode('utf8'))
    writer = csv.writer(response)
    writer.writerow(['Fecha', 'Asignado A', 'Concepto', 'Tipo', 'Monto', 'Estatus', 'Fecha Pago'])
    
    for a in adeudos:
        asignado = a.equipo.club if a.equipo else (a.jugador.nombres if a.jugador else 'General')
        fecha_pago = a.fecha_pago.strftime("%d/%m/%Y") if a.fecha_pago else 'N/A'
        writer.writerow([a.fecha_creacion.strftime("%d/%m/%Y"), asignado, a.concepto, a.get_tipo_adeudo_display(), f"${a.monto}", a.get_estado_display(), fecha_pago])
    return response

@login_required
@secretaria_required
def panel_disciplina(peticion):
    if peticion.method == 'POST':
        if 'btn_sancionar' in peticion.POST:
            form = SancionForm(peticion.POST)
            if form.is_valid():
                sancion = form.save(commit=False)
                monto = form.cleaned_data.get('monto_multa')
                if monto is not None:
                    sancion.monto_multa = monto
                ultima_temp = Temporada.objects.order_by('-fecha_inicio', '-id').first()
                if not ultima_temp:
                    messages.error(peticion, 'No hay ninguna temporada registrada. Crea una temporada antes de aplicar sanciones.')
                    return redirect('panel_disciplina')
                sancion.temporada = ultima_temp
                sancion.save()
                if sancion.jugador:
                    Adeudo.objects.create(
                        jugador=sancion.jugador, sancion=sancion,
                        tutor=sancion.jugador.tutor,
                        concepto=f"Multa por sanción: {sancion.tipo} - {sancion.motivo[:50]}",
                        monto=sancion.monto_multa, tipo_adeudo='MULTA', estado='PENDIENTE'
                    )
                messages.success(peticion, f'Sanción aplicada y multa de ${sancion.monto_multa} generada.')
                return redirect('panel_disciplina')
                
        elif 'btn_cumplir' in peticion.POST:
            sancion = get_object_or_404(Sancion, id=peticion.POST.get('sancion_id'))
            sancion.juegos_cumplidos += 1
            if sancion.juegos_cumplidos >= sancion.juegos_suspension: sancion.activa = False
            sancion.save()
            messages.success(peticion, 'Juego restado del castigo.')
            return redirect('panel_disciplina')

    sanciones_activas_lista = Sancion.objects.filter(activa=True).order_by('-fecha_sancion')
    paginator = Paginator(sanciones_activas_lista, 20)
    page_number = peticion.GET.get('page')
    sanciones_activas = paginator.get_page(page_number)
    historial = Sancion.objects.filter(activa=False).order_by('-fecha_sancion')[:20]
    jugadores_json = json.dumps(list(Jugador.objects.all().order_by(
        'apellido_paterno', 'nombres'
    ).values('id', 'nombres', 'apellido_paterno', 'apellido_materno')))

    return render(peticion, 'gestion/sanciones.html', {
        'sanciones_activas': sanciones_activas, 'historial': historial,
        'form_sancion': SancionForm(), 'jugadores_json': jugadores_json
    })


@login_required
def gestion_sanciones_jugador(peticion, jugador_id):
    jugador = get_object_or_404(Jugador, id=jugador_id)
    equipo = jugador.equipo
    if equipo and equipo.entrenador != peticion.user and not admin_o_secre_check(peticion.user):
        messages.error(peticion, 'No tienes permiso para ver las sanciones de este jugador.')
        return redirect('dashboard')
    sanciones = Sancion.objects.filter(jugador=jugador).order_by('-fecha_sancion')
    multas = Adeudo.objects.filter(jugador=jugador, tipo_adeudo='MULTA').order_by('-fecha_creacion')

    return render(peticion, 'gestion/sanciones_jugador.html', {
        'jugador': jugador, 'equipo': equipo,
        'sanciones': sanciones, 'multas': multas,
    })

# =========================================================
# GESTIÓN DE APROBACIONES Y CAMBIOS (SECRETARÍA)
# =========================================================
@login_required
def perfil_jugador(peticion, pk):
    jugador = get_object_or_404(
        Jugador.objects.select_related('equipo', 'tutor').prefetch_related(
            'torneos_participados__temporada', 'torneos_participados__equipo',
            'historial_equipos__equipo', 'sancion_set', 'adeudos_jugador'
        ), pk=pk
    )
    es_tutor = jugador.tutor and peticion.user == jugador.tutor
    es_entrenador = jugador.equipo and peticion.user == jugador.equipo.entrenador
    if not (es_tutor or es_entrenador or peticion.user.is_staff):
        messages.error(peticion, 'No tienes permiso para ver este perfil.')
        return redirect('dashboard')
    edad_deportiva = "N/A"
    
    if jugador.fecha_nacimiento:
        anio_actual = date.today().year
        fecha_corte = date(anio_actual, 1, 1)
        resta_anios = fecha_corte.year - jugador.fecha_nacimiento.year
        if (fecha_corte.month, fecha_corte.day) < (jugador.fecha_nacimiento.month, jugador.fecha_nacimiento.day):
            edad_deportiva = resta_anios - 1
        else:
            edad_deportiva = resta_anios
            
    torneos_jugados = jugador.torneos_participados.all()
    sanciones = jugador.sancion_set.all().order_by('-fecha_sancion')
    multas_impagas = [a for a in jugador.adeudos_jugador.all() if a.tipo_adeudo == 'MULTA' and not a.pagado]
    total_multas = sum(a.monto for a in multas_impagas)
    estatus = jugador.semaforo['estatus']
    color = jugador.semaforo['color']
    icono = jugador.semaforo['icono']
    mensaje_alerta = jugador.semaforo['mensaje']
    adeudo = next((a for a in jugador.adeudos_jugador.all() if a.tipo_adeudo == 'INSCRIPCION'), None)
    pago_validado = adeudo.pagado if adeudo else False

    try:
        config = ConfiguracionSistema.objects.get(pk=1)
    except ConfiguracionSistema.DoesNotExist:
        config = None
    return render(peticion, 'gestion/perfil_jugador.html', {
        'jugador': jugador, 'edad': edad_deportiva, 'anio_torneo': date.today().year,
        'torneos_jugados': torneos_jugados, 'sanciones': sanciones,
        'multas_impagas': multas_impagas, 'total_multas': total_multas,
        'estatus': estatus, 'color': color, 'icono': icono,
        'mensaje_alerta': mensaje_alerta, 'pago_validado': pago_validado, 'config': config,
        'es_admin_secre': admin_o_secre_check(peticion.user),
    })

@login_required
def dar_de_baja_jugador(peticion, jugador_id):
    if peticion.method == 'POST':
        jugador = get_object_or_404(Jugador, id=jugador_id)
        es_staff_o_secre = admin_o_secre_check(peticion.user)
        es_coach = hasattr(peticion.user, 'equipo_entrenado') and peticion.user.equipo_entrenado == jugador.equipo
        
        if es_staff_o_secre or es_coach:
            historial_actual = HistorialEquipo.objects.filter(jugador=jugador, fecha_salida__isnull=True).last()
            if historial_actual:
                historial_actual.fecha_salida = timezone.now().date()
                historial_actual.save()
                
            jugador.equipo = None
            jugador.validado = False
            jugador.estado_validacion = 'PENDIENTE'
            jugador.save()
            messages.success(peticion, f'El jugador {jugador.nombres} ha sido dado de baja del club. Ahora es Agente Libre.')
        else:
            messages.error(peticion, 'No tienes permisos para dar de baja a este jugador.')
    return redirect(peticion.META.get('HTTP_REFERER', '/') if peticion.META.get('HTTP_REFERER', '').startswith(peticion.build_absolute_uri('/')) else 'dashboard')

@login_required
def eliminar_jugador(peticion, pk):
    if peticion.method != 'POST':
        return redirect('dashboard')
    jugador = get_object_or_404(Jugador, pk=pk)
    
    if admin_o_secre_check(peticion.user):
        equipo_id = jugador.equipo.id if jugador.equipo else None
        
        historial_actual = HistorialEquipo.objects.filter(jugador=jugador, fecha_salida__isnull=True).last()
        if historial_actual:
            historial_actual.fecha_salida = timezone.now().date()
            historial_actual.save()
            
        jugador.equipo = None
        jugador.validado = False
        jugador.estado_validacion = 'PENDIENTE'
        jugador.activo = False 
        jugador.save()
        
        messages.success(peticion, 'Jugador desactivado y enviado al archivo de Bajas del sistema.')
        if equipo_id: return redirect('gestionar_equipo', equipo_id=equipo_id)
        return redirect('dashboard')
        
    messages.error(peticion, 'No tienes permisos para eliminar jugadores del sistema.')
    return redirect('dashboard')

@login_required
@secretaria_required
def panel_aprobaciones(peticion):
    pendientes_lista = Jugador.objects.filter(estado_validacion='PENDIENTE', activo=True).order_by('id').prefetch_related('adeudos_jugador')
    paginator = Paginator(pendientes_lista, 20)
    page_number = peticion.GET.get('page')
    jugadores_pendientes = paginator.get_page(page_number)
    pagos = {a.jugador_id for a in Adeudo.objects.filter(tipo_adeudo='INSCRIPCION', estado='PAGADO')}
    for p in jugadores_pendientes:
        p.pago_validado = p.id in pagos
    try:
        config = ConfiguracionSistema.objects.get(pk=1)
    except ConfiguracionSistema.DoesNotExist:
        config = None
    return render(peticion, 'gestion/panel_aprobaciones.html', {'jugadores_pendientes': jugadores_pendientes, 'config': config})

@login_required
@secretaria_required
def aprobar_jugador(peticion, pk):
    if peticion.method != 'POST':
        return redirect('panel_aprobaciones')
    jugador = get_object_or_404(Jugador, pk=pk)
    tiene_adeudo_pendiente = Adeudo.objects.filter(
        jugador=jugador, tipo_adeudo='INSCRIPCION'
    ).exclude(estado='PAGADO').exists()
    
    if tiene_adeudo_pendiente:
        messages.error(peticion, f"No puedes aprobar a {jugador.nombres}. Tiene adeudos de inscripción sin pagar.")
        return redirect('panel_aprobaciones')

    jugador.estado_validacion = 'APROBADO'
    jugador.validado = True
    jugador.motivo_rechazo = ""
    jugador.save()
    messages.success(peticion, f'{jugador.nombres} ha sido validado en el sistema.')
    return redirect('panel_aprobaciones')

@login_required
@secretaria_required
def rechazar_jugador(peticion, pk):
    if peticion.method != 'POST':
        return redirect('panel_aprobaciones')
    jugador = get_object_or_404(Jugador, pk=pk)
    jugador.estado_validacion = 'RECHAZADO'
    jugador.motivo_rechazo = 'Documentación incompleta o incorrecta.'
    jugador.intentos_registro += 1
    jugador.validado = False
    jugador.save()
    messages.warning(peticion, f"Registro de {jugador.nombres} rechazado.")
    return redirect('panel_aprobaciones')

@login_required
@secretaria_required
def rechazar_jugador_con_motivo(peticion, pk):
    if peticion.method == 'POST':
        jugador = get_object_or_404(Jugador, pk=pk)
        motivo = peticion.POST.get('motivo_rechazo', 'Documentos ilegibles o incorrectos.')
        jugador.estado_validacion = 'RECHAZADO'
        jugador.motivo_rechazo = motivo
        jugador.intentos_registro += 1
        jugador.validado = False
        jugador.save()
        messages.warning(peticion, f"Registro de {jugador.nombres} devuelto para corrección. Se ha notificado al tutor.")
    return redirect('panel_aprobaciones')

@login_required
@secretaria_required
def lista_cambios_equipo(peticion):
    solicitudes = SolicitudCambioEquipo.objects.filter(estado='PENDIENTE').select_related('jugador', 'equipo_origen', 'equipo_destino').order_by('-fecha_solicitud')
    return render(peticion, 'gestion/panel_cambios.html', {'solicitudes': solicitudes})

@login_required
@secretaria_required
def procesar_cambio_equipo(peticion, solicitud_id, accion):
    solicitud = get_object_or_404(SolicitudCambioEquipo, id=solicitud_id)
    if solicitud.estado != 'PENDIENTE':
        messages.warning(peticion, 'Esta solicitud ya fue procesada anteriormente.')
        return redirect('lista_cambios_equipo')
    if accion == 'aprobar':
        solicitud.estado = 'APROBADO'
        solicitud.fecha_resolucion = timezone.now()
        jugador = solicitud.jugador
        
        if solicitud.equipo_origen:
            historial_viejo = HistorialEquipo.objects.filter(jugador=jugador, equipo=solicitud.equipo_origen, fecha_salida__isnull=True).last()
            if historial_viejo:
                historial_viejo.fecha_salida = timezone.now().date()
                historial_viejo.save()
                
        jugador.equipo = solicitud.equipo_destino
        jugador.estado_validacion = 'PENDIENTE'
        jugador.validado = False
        jugador.save()
        HistorialEquipo.objects.create(jugador=jugador, equipo=solicitud.equipo_destino, motivo="Cambio de Equipo Aprobado")
        
        try:
            config = ConfiguracionSistema.objects.get(pk=1)
            costo = config.costo_inscripcion if config.costo_inscripcion else 0.00
        except ConfiguracionSistema.DoesNotExist:
            costo = 0.00
        Adeudo.objects.create(
            tutor=jugador.tutor, equipo=solicitud.equipo_destino, jugador=jugador,
            concepto=f"Inscripción por Cambio de Club - {jugador.nombres} {jugador.apellido_paterno}",
            monto=costo, tipo_adeudo='INSCRIPCION', estado='PENDIENTE'
        )
        messages.success(peticion, 'El cambio de equipo ha sido APROBADO y se ha generado el adeudo correspondiente en Finanzas.')
        
    elif accion == 'rechazar':
        solicitud.estado = 'RECHAZADO'
        solicitud.fecha_resolucion = timezone.now()
        messages.error(peticion, 'La solicitud de cambio de equipo ha sido RECHAZADA.')
        
    solicitud.save()
    return redirect('lista_cambios_equipo')

@login_required
def credencial_jugador(peticion, pk):
    jugador = get_object_or_404(Jugador, pk=pk, activo=True)
    es_tutor = hasattr(peticion.user, 'perfil') and jugador.tutor == peticion.user
    es_entrenador = hasattr(peticion.user, 'equipo_entrenado') and jugador.equipo and jugador.equipo.entrenador == peticion.user
    if not es_tutor and not es_entrenador and not peticion.user.is_staff:
        messages.error(peticion, 'No tienes permiso para ver la credencial de este jugador.')
        return redirect('dashboard')
    edad_deportiva = "N/A"
    if jugador.fecha_nacimiento:
        anio_actual = date.today().year
        fecha_corte = date(anio_actual, 1, 1)
        resta_anios = fecha_corte.year - jugador.fecha_nacimiento.year
        if (fecha_corte.month, fecha_corte.day) < (jugador.fecha_nacimiento.month, jugador.fecha_nacimiento.day): edad_deportiva = resta_anios - 1
        else: edad_deportiva = resta_anios
    return render(peticion, 'gestion/credencial.html', {'jugador': jugador, 'edad': edad_deportiva, 'anio_torneo': date.today().year})

# =========================================================
# MÓDULOS DE EXPORTACIÓN (PDF Y EXCEL)
# =========================================================
def link_callback(uri, rel):
    sUrl = settings.STATIC_URL
    sRoot = os.path.normpath(getattr(settings, 'STATIC_ROOT', None) or os.path.join(str(settings.BASE_DIR), 'gestion', 'static'))
    mUrl = settings.MEDIA_URL
    mRoot = os.path.normpath(settings.MEDIA_ROOT)
    if uri.startswith(mUrl):
        path = os.path.normpath(os.path.join(mRoot, uri.replace(mUrl, "")))
        if not path.startswith(mRoot):
            return ""
    elif uri.startswith(sUrl):
        path = os.path.normpath(os.path.join(sRoot, uri.replace(sUrl, "")))
        if not path.startswith(sRoot):
            return ""
    else: return ""
    if not os.path.isfile(path): return ""
    return path

@login_required
def generar_credencial_pdf(peticion, pk):
    """
    Genera una credencial PDF de afiliación visualmente idéntica a la imagen de muestra,
    con el código QR posicionado verticalmente arriba del texto de vigencia.
    """
    jugador = get_object_or_404(Jugador, pk=pk)
    es_tutor = jugador.tutor and peticion.user == jugador.tutor
    es_entrenador = jugador.equipo and peticion.user == jugador.equipo.entrenador
    if not (es_tutor or es_entrenador or peticion.user.is_staff):
        messages.error(peticion, 'No tienes permiso para generar esta credencial.')
        return redirect('dashboard')
    anio_actual = date.today().year
    fecha_corte = date(anio_actual, 1, 1)

    # Cálculo de edad deportiva (mantenido del diseño original)
    if not jugador.fecha_nacimiento:
        edad = "N/A"
    else:
        resta_anios = fecha_corte.year - jugador.fecha_nacimiento.year
        if (fecha_corte.month, fecha_corte.day) < (jugador.fecha_nacimiento.month, jugador.fecha_nacimiento.day):
            edad = resta_anios - 1
        else:
            edad = resta_anios

    # Rutas de archivos multimedia y estáticos
    mRoot = settings.MEDIA_ROOT
    foto_path = os.path.join(mRoot, jugador.foto_perfil.name) if jugador.foto_perfil else None
    qr_path = os.path.join(mRoot, jugador.codigo_qr.name) if jugador.codigo_qr else None
    
    ruta_estaticos = os.path.join(str(settings.BASE_DIR), 'gestion', 'static', 'gestion', 'img')
    logo_ademebaoaxaca_path = os.path.join(ruta_estaticos, 'logo_ademebaoaxaca.png')
    logo_fiba_path = os.path.join(ruta_estaticos, 'logo_fiba.png')
    firma_path = os.path.join(ruta_estaticos, 'firma_presidente.png')

    # Configuración del documento de respuesta HTTP
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'filename="credencial_afiliacion_{jugador.pk}.pdf"'

    # Dimensiones estándar CR-80 (86mm x 64mm)
    ancho_id = 86 * mm
    alto_id = 64 * mm
    c = canvas.Canvas(response, pagesize=(ancho_id, alto_id))
    
    # Colores institucionales de la muestra
    color_rojo = HexColor('#B22222')
    color_verde = HexColor('#228B22')
    
    # ==========================================
    #                 ANVERSO
    # ==========================================
    
    # Fondo base gris muy claro
    c.setFillColorRGB(0.96, 0.96, 0.96)
    c.rect(0, 0, ancho_id, alto_id, fill=1, stroke=0)

    # Marca de agua sutil en el fondo del anverso
    if os.path.exists(logo_ademebaoaxaca_path):
        c.setFillColorRGB(0.9, 0.9, 0.9, alpha=0.1)
        c.drawImage(logo_ademebaoaxaca_path, ancho_id*0.2, alto_id*0.15, width=25*mm, height=35*mm, preserveAspectRatio=True, mask='auto')

    # Polígonos de diseño del lateral izquierdo
    side_graphic_width = ancho_id * 0.16
    
    # Triángulo/Polígono Superior Rojo
    c.setFillColor(color_rojo)
    path_rojo = c.beginPath()
    path_rojo.moveTo(0, alto_id)
    path_rojo.lineTo(side_graphic_width, alto_id)
    path_rojo.lineTo(side_graphic_width, alto_id - 10*mm)
    path_rojo.lineTo(0, alto_id - 20*mm)
    path_rojo.close()
    c.drawPath(path_rojo, fill=1, stroke=0)
    
    # Polígono Inferior Verde
    c.setFillColor(color_verde)
    path_verde = c.beginPath()
    path_verde.moveTo(0, alto_id - 20*mm)
    path_verde.lineTo(side_graphic_width, alto_id - 10*mm)
    path_verde.lineTo(side_graphic_width, 0)
    path_verde.lineTo(0, 0)
    path_verde.close()
    c.drawPath(path_verde, fill=1, stroke=0)
    
    # Emblemas sobre la franja lateral izquierda
    if os.path.exists(logo_ademebaoaxaca_path):
        c.drawImage(logo_ademebaoaxaca_path, side_graphic_width/2 - 4*mm, alto_id - 20*mm, width=8*mm, height=12*mm, preserveAspectRatio=True, mask='auto')
    if os.path.exists(logo_fiba_path):
        c.drawImage(logo_fiba_path, side_graphic_width/2 - 4.5*mm, alto_id - 33*mm, width=9*mm, height=9*mm, preserveAspectRatio=True, mask='auto')
    
    # Encabezado principal (Texto en mayúsculas fijas)
    c.setFillColorRGB(0, 0, 0, alpha=1) # Restaurar opacidad del texto
    c.setFont("Helvetica-Bold", 6.5)
    c.drawCentredString(ancho_id/2 + side_graphic_width/2, alto_id - 5*mm, "CIRCUITO DE BASQUETBOL DEL")
    c.drawCentredString(ancho_id/2 + side_graphic_width/2, alto_id - 8*mm, "ESTADO DE OAXACA CIEBO A.C.")
    c.setFont("Helvetica-Bold", 7.5)
    c.drawCentredString(ancho_id/2 + side_graphic_width/2, alto_id - 11*mm, "ADEMEBA OAXACA")

    # Estructura del marco bicolor para la fotografía
    photo_frame_x = side_graphic_width + 4*mm
    photo_frame_y = alto_id - 42*mm
    photo_frame_width = 20*mm
    photo_frame_height = 25*mm
    
    # Líneas exteriores rojas (Esquina superior derecha)
    c.setStrokeColor(color_rojo)
    c.setLineWidth(1)
    path_frame_rojo = c.beginPath()
    path_frame_rojo.moveTo(photo_frame_x, photo_frame_y + photo_frame_height)
    path_frame_rojo.lineTo(photo_frame_x + photo_frame_width, photo_frame_y + photo_frame_height)
    path_frame_rojo.lineTo(photo_frame_x + photo_frame_width, photo_frame_y)
    c.drawPath(path_frame_rojo, fill=0, stroke=1)
    
    # Líneas exteriores verdes (Esquina inferior izquierda)
    c.setStrokeColor(color_verde)
    path_frame_verde = c.beginPath()
    path_frame_verde.moveTo(photo_frame_x + photo_frame_width, photo_frame_y)
    path_frame_verde.lineTo(photo_frame_x, photo_frame_y)
    path_frame_verde.lineTo(photo_frame_x, photo_frame_y + photo_frame_height)
    c.drawPath(path_frame_verde, fill=0, stroke=1)
    
    # Inserción de la fotografía del jugador
    if foto_path and os.path.exists(foto_path):
        c.drawImage(foto_path, photo_frame_x + 1*mm, photo_frame_y + 1*mm, width=photo_frame_width - 2*mm, height=photo_frame_height - 2*mm, preserveAspectRatio=True, mask='auto')

    # Bloque informativo de datos personales (Derecha de la foto)
    info_x = photo_frame_x + photo_frame_width + 5*mm
    c.setFillColorRGB(0, 0, 0)
    
    # Segmentación estética del nombre completo en dos líneas
    nombre_completo = f"{jugador.nombres} {jugador.apellido_paterno} {jugador.apellido_materno}".strip().upper()
    partes_nombre = nombre_completo.split(' ', 1)
    nombre_linea_1 = partes_nombre[0] if len(partes_nombre) > 0 else ""
    nombre_linea_2 = partes_nombre[1] if len(partes_nombre) > 1 else ""

    # Impresión del nombre del jugador
    c.setFont("Helvetica-Bold", 7)
    c.drawString(info_x, alto_id - 20*mm, "JUGADOR:")
    c.setFont("Helvetica-Bold", 8)
    c.drawString(info_x, alto_id - 23*mm, nombre_linea_1)
    c.drawString(info_x, alto_id - 26*mm, nombre_linea_2)

    # Impresión del Club de procedencia
    c.setFont("Helvetica-Bold", 7)
    c.drawString(info_x, alto_id - 31*mm, "CLUB:")
    c.setFont("Helvetica-Bold", 8)
    club_text = (jugador.equipo.club if jugador.equipo else 'SIN CLUB').upper()
    c.drawString(info_x, alto_id - 34*mm, club_text)
    
    # Firma oficial del presidente (Fondo transparente)
    centro_x = ancho_id / 2 + side_graphic_width / 2
    if os.path.exists(firma_path):
        c.drawImage(firma_path, centro_x - 15*mm, 10*mm, width=30*mm, height=15*mm, preserveAspectRatio=True, mask='auto')

    # Textos institucionales inferiores del anverso
    c.setFont("Helvetica", 4.5)
    c.drawCentredString(ancho_id/2 + side_graphic_width/2, 5*mm, "ARQ. LUIS CARPIO PÉREZ")
    c.drawCentredString(ancho_id/2 + side_graphic_width/2, 3.5*mm, "PRESIDENTE DEL CIEBO A.C.")
    c.drawCentredString(ancho_id/2 + side_graphic_width/2, 2*mm, "ADEMEBA OAXACA")

    # Cambio a la siguiente página del lienzo (Reverso)
    c.showPage()
    
    # ==========================================
    #                 REVERSO
    # ==========================================
    
    # Fondo base gris claro para el reverso
    c.setFillColorRGB(0.96, 0.96, 0.96)
    c.rect(0, 0, ancho_id, alto_id, fill=1, stroke=0)
    
    # Esquinas decorativas superiores del reverso (Derecha)
    c.setFillColor(color_rojo)
    path_back_rojo_top = c.beginPath()
    path_back_rojo_top.moveTo(ancho_id - 5*mm, alto_id)
    path_back_rojo_top.lineTo(ancho_id, alto_id - 10*mm)
    path_back_rojo_top.lineTo(ancho_id, alto_id)
    path_back_rojo_top.close()
    c.drawPath(path_back_rojo_top, fill=1, stroke=0)
    
    c.setFillColorRGB(0.14, 0.55, 0.14, alpha=0.3)
    path_back_verde_top = c.beginPath()
    path_back_verde_top.moveTo(ancho_id - 12*mm, alto_id)
    path_back_verde_top.lineTo(ancho_id - 5*mm, alto_id - 7*mm)
    path_back_verde_top.lineTo(ancho_id - 5*mm, alto_id)
    path_back_verde_top.close()
    c.drawPath(path_back_verde_top, fill=1, stroke=0)

    # Marca de agua institucional centrada en el reverso
    if os.path.exists(logo_ademebaoaxaca_path):
        c.setFillColorRGB(0.92, 0.92, 0.92, alpha=0.08)
        c.drawImage(logo_ademebaoaxaca_path, ancho_id/2 - 15*mm, alto_id*0.08, width=30*mm, height=42*mm, preserveAspectRatio=True, mask='auto')

    # Coordenadas base para las etiquetas de información del reverso
    x_start_back = 10*mm
    y_start_fields = alto_id - 15*mm
    field_height = 8*mm
    
    def draw_back_field(canvas, x, y, label, data):
        canvas.setFillColorRGB(0, 0, 0, alpha=1)
        canvas.setFont("Helvetica-Bold", 6.5)
        canvas.drawString(x, y, label)
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.drawString(x, y - 3.5*mm, str(data).upper())

    # Renderizado secuencial de campos obligatorios
    draw_back_field(c, x_start_back, y_start_fields, "NO. AFILIACIÓN:", (jugador.numero_afiliacion or 'PENDIENTE'))
    y_start_fields -= field_height
    
    draw_back_field(c, x_start_back, y_start_fields, "REGIÓN:", getattr(jugador, 'region', 'VALLES CENTRALES'))
    y_start_fields -= field_height
    
    draw_back_field(c, x_start_back, y_start_fields, "CURP:", jugador.curp)
    y_start_fields -= field_height
    
    draw_back_field(c, x_start_back, y_start_fields, "TIPO DE SANGRE:", jugador.tipo_sangre)
    y_start_fields -= field_height
    
    # Procesamiento dinámico del número telefónico de contacto
    telefono_resp = ''
    if getattr(jugador, 'telefono_credencial', None): telefono_resp = str(jugador.telefono_credencial).strip()
    elif jugador.tutor and hasattr(jugador.tutor, 'perfil') and getattr(jugador.tutor.perfil, 'telefono', None): 
        telefono_resp = str(jugador.tutor.perfil.telefono).strip()
    if not telefono_resp or telefono_resp.lower() == 'none': telefono_resp = 'SIN TEL'
    
    draw_back_field(c, x_start_back, y_start_fields, "TELÉFONO:", telefono_resp)
    
    # ==========================================
    # CÓDIGO QR Y VIGENCIA (LADO DERECHO)
    # ==========================================
    # Definición de la línea de eje central para equilibrar ambos componentes
    qr_x_center = ancho_id - 18 * mm 
    qr_size = 18 * mm
    
    if qr_path and os.path.exists(qr_path):
        # El QR se dibuja elevado sobre el eje 'Y'
        qr_y = 20 * mm
        qr_x = qr_x_center - (qr_size / 2)
        c.drawImage(qr_path, qr_x, qr_y, width=qr_size, height=qr_size, preserveAspectRatio=True)

    # Texto de vigencia centrado milimétricamente bajo la caja del QR
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(qr_x_center, 15 * mm, f"VIGENCIA {anio_actual}-{anio_actual + 1}")

    # ==========================================
    #     Formas geométricas base inferiores
    # ==========================================
    c.setFillColor(color_verde)
    path_back_verde_bot = c.beginPath()
    path_back_verde_bot.moveTo(ancho_id/2 - 2*mm, 0)
    path_back_verde_bot.lineTo(ancho_id/2, 3*mm)
    path_back_verde_bot.lineTo(ancho_id/2 - 4*mm, 0)
    path_back_verde_bot.close()
    c.drawPath(path_back_verde_bot, fill=1, stroke=0)
    
    c.setFillColor(color_rojo)
    path_back_rojo_bot = c.beginPath()
    path_back_rojo_bot.moveTo(ancho_id/2, 0)
    path_back_rojo_bot.lineTo(ancho_id/2 + 2*mm, 3*mm)
    path_back_rojo_bot.lineTo(ancho_id/2 + 4*mm, 0)
    path_back_rojo_bot.close()
    c.drawPath(path_back_rojo_bot, fill=1, stroke=0)

    # Finalizar renderizado y guardar el flujo binario
    c.save()
    return response

@login_required
def generar_cedula_pdf(peticion, temporada_id, equipo_id):
    temporada = get_object_or_404(Temporada, id=temporada_id)
    equipo = get_object_or_404(Equipo, id=equipo_id)
    if equipo.entrenador != peticion.user and not peticion.user.is_staff: return redirect('dashboard')
        
    inscripcion = get_object_or_404(InscripcionTorneo, temporada=temporada, equipo=equipo)
    jugadores_list = list(inscripcion.jugadores.all().order_by('apellido_paterno', 'apellido_materno'))
    pares_jugadores = [jugadores_list[i:i + 2] for i in range(0, len(jugadores_list), 2)]
    staff_miembros = equipo.miembros_staff.all().order_by('cargo')
    perfil_entrenador, _ = PerfilEntrenador.objects.get_or_create(usuario=equipo.entrenador) if equipo.entrenador else (None, False)
    
    contexto = {'temporada': temporada, 'equipo': equipo, 'pares_jugadores': pares_jugadores, 'staff_miembros': staff_miembros, 'perfil_entrenador': perfil_entrenador}
    from django.template.loader import render_to_string
    from xhtml2pdf import pisa
    
    html = render_to_string('gestion/pdfs/cedula_equipo.html', contexto)
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'filename="Cedula_{equipo.club}.pdf"'
    
    pisa_status = pisa.CreatePDF(html, dest=response, link_callback=link_callback)
    if pisa_status.err: return HttpResponse('Error al generar PDF', status=500)
    return response

@login_required
def descargar_roster_excel(peticion, temporada_id, equipo_id):
    temporada = get_object_or_404(Temporada, id=temporada_id)
    equipo = get_object_or_404(Equipo, id=equipo_id)
    if equipo.entrenador != peticion.user and not peticion.user.is_staff: return redirect('dashboard')
        
    inscripcion = get_object_or_404(InscripcionTorneo, temporada=temporada, equipo=equipo)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="Roster_{equipo.club}_{temporada.nombre}.csv"'
    response.write('\ufeff'.encode('utf8'))
    
    writer = csv.writer(response)
    writer.writerow(['No. Camiseta', 'Apellido Paterno', 'Apellido Materno', 'Nombre(s)', 'CURP', 'Año Nacimiento', 'Rama', 'Posición', 'Num. Afiliación'])
    
    jugadores = inscripcion.jugadores.all().order_by('apellido_paterno')
    for j in jugadores: 
        anio_nac = j.fecha_nacimiento.year if j.fecha_nacimiento else 'N/A'
        writer.writerow([j.numero_camiseta or '-', j.apellido_paterno, j.apellido_materno, j.nombres, j.curp, anio_nac, j.rama, j.posicion, j.numero_afiliacion or 'PENDIENTE'])
    return response

# =========================================================
# LÓGICA DE PARTIDOS Y TABLA DE POSICIONES
# =========================================================
def calcular_posiciones(temporada):
    equipos_stats = {}
    for inscripcion in temporada.inscripciones.select_related('equipo').all():
        equipos_stats[inscripcion.equipo.id] = {'equipo': inscripcion.equipo, 'pj': 0, 'pg': 0, 'pp': 0, 'pf': 0, 'pc': 0, 'dif': 0, 'pts': 0}
        
    partidos_jugados = temporada.partidos.filter(jugado=True)
    for p in partidos_jugados:
        l_id = p.equipo_local.id
        v_id = p.equipo_visitante.id
        if l_id in equipos_stats and v_id in equipos_stats:
            equipos_stats[l_id]['pj'] += 1
            equipos_stats[v_id]['pj'] += 1
            equipos_stats[l_id]['pf'] += p.puntos_local
            equipos_stats[l_id]['pc'] += p.puntos_visitante
            equipos_stats[v_id]['pf'] += p.puntos_visitante
            equipos_stats[v_id]['pc'] += p.puntos_local
            
            if p.puntos_local > p.puntos_visitante: 
                equipos_stats[l_id]['pg'] += 1
                equipos_stats[l_id]['pts'] += 2
                equipos_stats[v_id]['pp'] += 1
                equipos_stats[v_id]['pts'] += 1
            elif p.puntos_visitante > p.puntos_local: 
                equipos_stats[v_id]['pg'] += 1
                equipos_stats[v_id]['pts'] += 2
                equipos_stats[l_id]['pp'] += 1
                equipos_stats[l_id]['pts'] += 1
                
    for stat in equipos_stats.values(): stat['dif'] = stat['pf'] - stat['pc']
    tabla = list(equipos_stats.values())
    tabla.sort(key=lambda x: (x['pts'], x['dif']), reverse=True)
    return tabla

@login_required
@secretaria_required
def gestionar_partidos(peticion, temporada_id):
    temporada = get_object_or_404(Temporada, id=temporada_id)

    equipos_inscritos = Equipo.objects.filter(torneos_jugados__temporada=temporada, torneos_jugados__validada=True)

    if peticion.method == 'POST':
        if 'btn_crear_partido' in peticion.POST:
            form_partido = PartidoForm(peticion.POST)
            form_partido.fields['equipo_local'].queryset = equipos_inscritos
            form_partido.fields['equipo_visitante'].queryset = equipos_inscritos
            if form_partido.is_valid():
                nuevo_partido = form_partido.save(commit=False)
                nuevo_partido.temporada = temporada
                nuevo_partido.save()
                messages.success(peticion, 'Partido programado con éxito.')
                return redirect('gestionar_partidos', temporada_id=temporada.id)
                
        elif 'btn_resultado' in peticion.POST:
            partido_id = peticion.POST.get('partido_id')
            partido = get_object_or_404(Partido, id=partido_id)
            form_resultado = ResultadoForm(peticion.POST, instance=partido)
            if form_resultado.is_valid(): 
                form_resultado.save()
                messages.success(peticion, 'Marcador actualizado correctamente.')
                return redirect('gestionar_partidos', temporada_id=temporada.id)

    form_partido = PartidoForm()
    form_partido.fields['equipo_local'].queryset = equipos_inscritos
    form_partido.fields['equipo_visitante'].queryset = equipos_inscritos
    
    partidos = temporada.partidos.select_related('equipo_local', 'equipo_visitante').all().order_by('fecha_hora', 'jornada')
    tabla_posiciones = calcular_posiciones(temporada)

    return render(peticion, 'gestion/gestionar_partidos.html', {
        'temporada': temporada, 'partidos': partidos, 'form_partido': form_partido, 
        'tabla_posiciones': tabla_posiciones, 'hay_equipos_validados': equipos_inscritos.exists()
    })

@login_required
@secretaria_required
def descargar_resultados_excel(peticion, temporada_id):
    temporada = get_object_or_404(Temporada, id=temporada_id)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="Resultados_{temporada.nombre}.csv"'
    response.write('\ufeff'.encode('utf8'))
    writer = csv.writer(response)
    
    writer.writerow(['--- TABLA DE POSICIONES ---'])
    writer.writerow(['Posición', 'Equipo', 'Partidos Jugados', 'Ganados', 'Perdidos', 'Puntos a Favor', 'Puntos en Contra', 'Diferencia', 'PTS TOTALES'])
    
    tabla = calcular_posiciones(temporada)
    for i, fila in enumerate(tabla, 1): 
        writer.writerow([i, fila['equipo'].club, fila['pj'], fila['pg'], fila['pp'], fila['pf'], fila['pc'], fila['dif'], fila['pts']])
        
    writer.writerow([])
    writer.writerow(['--- HISTORIAL DE PARTIDOS ---'])
    writer.writerow(['Jornada', 'Equipo Local', 'Pts Local', 'Pts Visitante', 'Equipo Visitante', 'Cancha', 'Fecha y Hora', 'Estatus'])
    
    partidos = temporada.partidos.select_related('equipo_local', 'equipo_visitante').all().order_by('fecha_hora', 'jornada')
    for p in partidos: 
        fecha_str = p.fecha_hora.strftime("%d/%m/%Y %H:%M") if p.fecha_hora else "Por definir"
        estatus_str = "Finalizado" if p.jugado else "Pendiente"
        writer.writerow([p.jornada, p.equipo_local.club, p.puntos_local, p.puntos_visitante, p.equipo_visitante.club, p.cancha, fecha_str, estatus_str])
        
    return response

# =========================================================
# ARCHIVO HISTÓRICO
# =========================================================
@login_required
@secretaria_required
def archivo_index(peticion): 
    anios_con_torneos = Temporada.objects.filter(campeon__isnull=False).dates('fecha_inicio', 'year').reverse()
    lista_anios = [fecha.year for fecha in anios_con_torneos]
    return render(peticion, 'gestion/archivo_index.html', {'anios': lista_anios})

@login_required
@secretaria_required
def archivo_historico_anio(peticion, anio): 
    temporadas_del_anio = Temporada.objects.filter(fecha_inicio__year=anio, campeon__isnull=False).order_by('-fecha_inicio')
    return render(peticion, 'gestion/historico_anio.html', {'anio_buscado': anio, 'temporadas': temporadas_del_anio})

@login_required
@secretaria_required
def archivo_historico_detalle(peticion, temporada_id):
    temporada_historica = get_object_or_404(Temporada, id=temporada_id)
    
    # SOLUCIÓN HUECO 3: También evitamos la alerta N+1 en el archivo histórico
    inscripciones = temporada_historica.inscripciones.prefetch_related('jugadores').order_by('equipo__club')
    partidos = temporada_historica.partidos.all().order_by('jornada')
    tabla_posiciones = calcular_posiciones(temporada_historica)
    
    return render(peticion, 'gestion/historico_detalle.html', {
        'temporada': temporada_historica, 'inscripciones': inscripciones, 
        'partidos': partidos, 'tabla_posiciones': tabla_posiciones
    })

# =========================================================
# LÓGICA DE PAGO PARA TUTORES Y ENTRENADORES
# =========================================================
@login_required
def subir_voucher_adeudo(peticion, adeudo_id):
    adeudo = get_object_or_404(Adeudo, id=adeudo_id)
    es_su_adeudo = False
    if adeudo.tutor == peticion.user: es_su_adeudo = True
    elif adeudo.equipo and adeudo.equipo.entrenador == peticion.user: es_su_adeudo = True
        
    if not es_su_adeudo and not peticion.user.is_staff:
        messages.error(peticion, 'No tienes permiso para gestionar este adeudo.')
        return redirect('dashboard')
        
    if peticion.method == 'POST':
        form = VoucherForm(peticion.POST, peticion.FILES, instance=adeudo)
        if form.is_valid():
            adeudo_guardado = form.save(commit=False)
            adeudo_guardado.estado = 'REVISION'
            adeudo_guardado.save()
            messages.success(peticion, 'Comprobante enviado. El equipo administrativo validará tu pago en breve.')
            return redirect('dashboard')
    else:
        form = VoucherForm(instance=adeudo)
    try:
        config = ConfiguracionSistema.objects.get(pk=1)
    except ConfiguracionSistema.DoesNotExist:
        config = None
    return render(peticion, 'gestion/subir_voucher.html', {'form': form, 'adeudo': adeudo, 'config': config})

@login_required
@secretaria_required
def panel_configuracion(peticion):
    config, creado = ConfiguracionSistema.objects.get_or_create(pk=1)
    if peticion.method == 'POST':
        form = ConfiguracionSistemaForm(peticion.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(peticion, 'Configuración global actualizada.')
            return redirect('panel_configuracion')
    else:
        form = ConfiguracionSistemaForm(instance=config)
    return render(peticion, 'gestion/panel_configuracion.html', {'form': form, 'config': config})


def solicitar_cambio_contrasena(peticion):
    if peticion.user.is_authenticated:
        messages.info(peticion, 'Ya has iniciado sesión. Si deseas cambiar tu contraseña, contacta al administrador.')
        return redirect('dashboard')
    if peticion.method == 'POST':
        email = peticion.POST.get('email', '').strip()
        if email:
            usuarios = User.objects.filter(email=email)
            if usuarios.exists():
                usuario = usuarios.first()
                pendiente = SolicitudCambioContrasena.objects.filter(usuario=usuario, estado='PENDIENTE').exists()
                if pendiente:
                    pass
                else:
                    SolicitudCambioContrasena.objects.filter(usuario=usuario).exclude(estado='PENDIENTE').delete()
                    SolicitudCambioContrasena.objects.create(usuario=usuario)
            messages.success(peticion, 'Si el correo está registrado, recibirás instrucciones para cambiar tu contraseña.')
            return redirect(f'{reverse("verificar_solicitud_contrasena")}?email={email}')
        else:
            messages.error(peticion, 'Ingresa tu correo electrónico.')
    return render(peticion, 'gestion/solicitar_cambio_contrasena.html', {})


def verificar_solicitud_contrasena(peticion):
    email = peticion.GET.get('email', '').strip()
    return render(peticion, 'gestion/verificar_solicitud_contrasena.html', {
        'email_consultado': email,
    })


@login_required
@secretaria_required
def lista_solicitudes_contrasena(peticion):
    solicitudes = SolicitudCambioContrasena.objects.all().order_by('-fecha_solicitud')
    if peticion.method == 'POST':
        solicitud_id = peticion.POST.get('solicitud_id')
        accion = peticion.POST.get('accion')
        solicitud = get_object_or_404(SolicitudCambioContrasena, id=solicitud_id)
        if accion == 'aprobar':
            from django.utils.crypto import get_random_string
            temp_password = get_random_string(length=16)
            solicitud.usuario.set_password(temp_password)
            solicitud.usuario.save()
            solicitud.estado = 'APROBADA'
            solicitud.save()
            messages.success(peticion, f'Solicitud aprobada. La contraseña temporal se ha asignado al usuario. Entrégala personalmente o compártela por un medio seguro.')
        elif accion == 'rechazar':
            motivo = peticion.POST.get('motivo_rechazo', '').strip()
            if not motivo:
                messages.error(peticion, 'Debes escribir un motivo para rechazar la solicitud.')
                return redirect('lista_solicitudes_contrasena')
            solicitud.estado = 'RECHAZADA'
            solicitud.motivo_rechazo = motivo
            solicitud.save()
            messages.warning(peticion, f'Solicitud rechazada. Motivo: {motivo}')
        return redirect('lista_solicitudes_contrasena')
    return render(peticion, 'gestion/lista_solicitudes_contrasena.html', {'solicitudes': solicitudes})


@login_required
def cambiar_contrasena(peticion):
    if peticion.method == 'POST':
        actual = peticion.POST.get('actual', '')
        nueva = peticion.POST.get('nueva', '')
        confirmar = peticion.POST.get('confirmar', '')
        if not peticion.user.check_password(actual):
            messages.error(peticion, 'La contraseña actual es incorrecta.')
        elif len(nueva) < 8:
            messages.error(peticion, 'La nueva contraseña debe tener al menos 8 caracteres.')
        elif nueva != confirmar:
            messages.error(peticion, 'Las contraseñas no coinciden.')
        else:
            from django.contrib.auth.password_validation import validate_password
            try:
                validate_password(nueva, peticion.user)
            except Exception as e:
                for error in e.messages:
                    messages.error(peticion, error)
                return render(peticion, 'gestion/cambiar_contrasena.html', {})
            peticion.user.set_password(nueva)
            peticion.user.save()
            update_session_auth_hash(peticion, peticion.user)
            messages.success(peticion, 'Contraseña actualizada correctamente.')
    return render(peticion, 'gestion/cambiar_contrasena.html', {})


@login_required
def pagar_multa(peticion, sancion_id):
    sancion = get_object_or_404(Sancion, id=sancion_id)
    adeudo = Adeudo.objects.filter(sancion=sancion).first()
    if not adeudo:
        messages.error(peticion, 'No se encontró el adeudo asociado a esta sanción.')
        return redirect('dashboard')
    
    es_tutor = adeudo.jugador and adeudo.jugador.tutor == peticion.user
    es_staff = admin_o_secre_check(peticion.user)
    
    if not es_tutor and not es_staff:
        messages.error(peticion, 'No tienes permiso para pagar esta multa.')
        return redirect('dashboard')
    
    if peticion.method == 'POST':
        form = VoucherForm(peticion.POST, peticion.FILES, instance=adeudo)
        if form.is_valid():
            adeudo_guardado = form.save(commit=False)
            adeudo_guardado.estado = 'REVISION'
            adeudo_guardado.save()
            messages.success(peticion, 'Comprobante de pago enviado. El administrador lo validará.')
            return redirect('dashboard')
    else:
        form = VoucherForm(instance=adeudo)
    
    try:
        config = ConfiguracionSistema.objects.get(pk=1)
    except ConfiguracionSistema.DoesNotExist:
        config = None
    return render(peticion, 'gestion/subir_voucher.html', {'form': form, 'adeudo': adeudo, 'config': config})


@login_required
def validar_jugador_qr(peticion, pk):
    jugador = get_object_or_404(Jugador, pk=pk)
    if not peticion.user.is_staff and not hasattr(peticion.user, 'equipo_entrenado'):
        messages.error(peticion, 'No tienes permiso para ver el perfil de este jugador.')
        return redirect('dashboard')
    estatus = jugador.semaforo['estatus']
    color = jugador.semaforo['color']
    icono = jugador.semaforo['icono']
    mensaje_alerta = jugador.semaforo['mensaje']
    nombres_torneos = jugador.ligas_actuales
    context = {'jugador': jugador, 'estatus': estatus, 'color': color, 'icono': icono, 'mensaje_alerta': mensaje_alerta, 'torneos': nombres_torneos}
    return render(peticion, 'gestion/public_perfil.html', context)

@login_required
def lista_jugadores_baja(request):
    if not admin_o_secre_check(request.user): return redirect('dashboard') 
    jugadores_baja = Jugador.objects.filter(activo=False).order_by('-id')
    return render(request, 'gestion/jugadores_baja.html', {'jugadores': jugadores_baja})

@login_required
def reactivar_jugador(request, pk):
    if request.method != 'POST':
        return redirect('dashboard')
    if not admin_o_secre_check(request.user): return redirect('dashboard')
    jugador = get_object_or_404(Jugador, pk=pk)
    jugador.activo = True
    jugador.estado_validacion = 'PENDIENTE'
    jugador.save()
    
    try:
        config = ConfiguracionSistema.objects.get(pk=1)
        costo = config.costo_inscripcion if config.costo_inscripcion else 0.00
    except ConfiguracionSistema.DoesNotExist:
        costo = 0.00
    Adeudo.objects.create(
        tutor=jugador.tutor, jugador=jugador,
        concepto=f"Inscripción por Reactivación - {jugador.nombres} {jugador.apellido_paterno}",
        monto=costo, tipo_adeudo='INSCRIPCION', estado='PENDIENTE'
    )
    
    messages.success(request, f"¡El jugador {jugador.nombres} ha sido reactivado (Agente Libre) y se generó el cobro!")
    return redirect('jugadores_baja')

@login_required
@secretaria_required
def validar_inscripcion(peticion, inscripcion_id):
    if peticion.method != 'POST':
        return redirect('dashboard')
    inscripcion = get_object_or_404(InscripcionTorneo, id=inscripcion_id)
    inscripcion.validada = True
    inscripcion.save()
    messages.success(peticion, f"¡La inscripción del equipo {inscripcion.equipo.club} ha sido VALIDADA! Ahora aparecerán en el rol de juegos.")
    return redirect('detalle_temporada', temporada_id=inscripcion.temporada.id)

@login_required
def mis_jugadores(peticion):
    jugadores_lista = Jugador.objects.filter(tutor=peticion.user).prefetch_related('sancion_set', 'adeudos_jugador')
    for j in jugadores_lista:
        j.sanciones_count = sum(1 for s in j.sancion_set.all() if s.activa)
        j.multas_impagas = [a for a in j.adeudos_jugador.all() if a.tipo_adeudo == 'MULTA' and not a.pagado]
        j.total_multas = sum(a.monto for a in j.multas_impagas)
    return render(peticion, 'gestion/mis_jugadores.html', {'jugadores': jugadores_lista})


# =========================================================
# MÓDULO DE REEMBOLSOS
# =========================================================

@login_required
def solicitar_reembolso(peticion, jugador_id):
    jugador = get_object_or_404(Jugador, id=jugador_id, tutor=peticion.user)
    if jugador.estado_validacion != 'RECHAZADO':
        messages.error(peticion, 'Solo puedes solicitar reembolso si tu jugador fue rechazado.')
        return redirect('dashboard')

    adeudo_pagado = Adeudo.objects.filter(
        jugador=jugador, tipo_adeudo='INSCRIPCION', pagado=True
    ).first()

    if not adeudo_pagado:
        messages.error(peticion, 'No hay un pago registrado para este jugador. No es necesario solicitar reembolso.')
        return redirect('dashboard')

    if Reembolso.objects.filter(jugador=jugador, procesado=False).exists():
        messages.warning(peticion, 'Ya tienes una solicitud de reembolso activa para este jugador.')
        return redirect('dashboard')

    if peticion.method == 'POST':
        banco = peticion.POST.get('banco', '').strip()
        numero_cuenta = peticion.POST.get('numero_cuenta', '').strip()
        titular = peticion.POST.get('titular', '').strip()
        if not banco or not numero_cuenta or not titular:
            messages.error(peticion, 'Todos los campos bancarios son obligatorios.')
        else:
            Reembolso.objects.create(
                jugador=jugador, tutor=peticion.user, adeudo=adeudo_pagado,
                banco=banco, numero_cuenta=numero_cuenta, titular=titular,
                monto=adeudo_pagado.monto,
            )
            messages.success(peticion, f'Solicitud de reembolso enviada. Te contactaremos para devolver ${adeudo_pagado.monto}.')
            return redirect('dashboard')

    bancos_sugeridos = ['BBVA', 'Santander', 'Banamex', 'Banorte', 'HSBC', 'Scotiabank', 'Azteca', 'Bancoppel', 'Afirme', 'Interacciones']
    return render(peticion, 'gestion/solicitar_reembolso.html', {
        'jugador': jugador, 'adeudo': adeudo_pagado, 'bancos_sugeridos': bancos_sugeridos,
    })


@login_required
@user_passes_test(admin_o_secre_check)
def panel_reembolsos(peticion):
    pendientes = Reembolso.objects.filter(procesado=False).select_related('jugador', 'tutor', 'adeudo').order_by('-fecha_solicitud')
    procesados = Reembolso.objects.filter(procesado=True).select_related('jugador', 'tutor', 'adeudo').order_by('-fecha_procesado')[:20]
    return render(peticion, 'gestion/panel_reembolsos.html', {
        'pendientes': pendientes, 'procesados': procesados,
        'es_admin_secre': True,
    })


@login_required
@user_passes_test(admin_o_secre_check)
def procesar_reembolso(peticion, pk):
    if peticion.method != 'POST':
        return redirect('panel_reembolsos')
    reembolso = get_object_or_404(Reembolso, pk=pk)
    if reembolso.procesado:
        messages.warning(peticion, 'Este reembolso ya fue procesado.')
        return redirect('panel_reembolsos')

    reembolso.procesado = True
    reembolso.fecha_procesado = timezone.now()
    reembolso.save()

    adeudo = reembolso.adeudo
    if adeudo:
        adeudo.estado = 'PENDIENTE'
        adeudo.pagado = False
        adeudo.voucher_comprobante = None
        adeudo.fecha_pago = None
        adeudo.save()

    messages.success(peticion, f'Reembolso de ${reembolso.monto} marcado como procesado.')
    return redirect('panel_reembolsos')