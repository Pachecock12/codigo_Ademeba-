from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from django.conf import settings
from django.urls import reverse
import qrcode
import uuid
import os
from io import BytesIO
from django.core.files import File
from PIL import Image
from datetime import date
from django.utils import timezone

REGIONES = [
    ('Valles Centrales', 'Valles Centrales'), 
    ('Istmo', 'Istmo'), 
    ('Papaloapan', 'Papaloapan'), 
    ('Sierra Sur', 'Sierra Sur'), 
    ('Sierra Norte', 'Sierra Norte'), 
    ('Costa', 'Costa'), 
    ('Cañada', 'Cañada'), 
    ('Mixteca', 'Mixteca')
]

class Jugador(models.Model):
    RAMAS = [
        ('Varonil', 'Varonil'), 
        ('Femenil', 'Femenil')
    ]
    
    POSICIONES = [
        ('Base', 'Base'), 
        ('Escolta', 'Escolta'), 
        ('Alero', 'Alero'), 
        ('Ala-Pívot', 'Ala-Pívot'), 
        ('Pívot', 'Pívot')
    ]
    
    SANGRE = [
        ('O+', 'O+'), ('O-', 'O-'), 
        ('A+', 'A+'), ('A-', 'A-'), 
        ('B+', 'B+'), ('B-', 'B-'), 
        ('AB+', 'AB+'), ('AB-', 'AB-')
    ]
    
    ESTADOS = [
        ('PENDIENTE', 'Pendiente de Revisión'),
        ('APROBADO', 'Aprobado'),
        ('RECHAZADO', 'Rechazado por Corrección')
    ]

    nombres = models.CharField(max_length=100)
    apellido_paterno = models.CharField(max_length=100)
    apellido_materno = models.CharField(max_length=100)
    curp = models.CharField(max_length=18, unique=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    rama = models.CharField(max_length=10, choices=RAMAS, db_index=True)
    numero_camiseta = models.CharField(max_length=3, blank=True, null=True)
    posicion = models.CharField(max_length=20, choices=POSICIONES)
    tipo_sangre = models.CharField(max_length=5, choices=SANGRE)
    region = models.CharField(max_length=50, choices=REGIONES)
    municipio_vive = models.CharField(max_length=100)
    telefono_credencial = models.CharField(max_length=15)
    
    foto_perfil = models.ImageField(upload_to='jugadores/fotos/')
    archivo_curp = models.FileField(upload_to='jugadores/curp/')
    archivo_identificacion = models.FileField(upload_to='jugadores/id/')
    acta_nacimiento = models.FileField(upload_to='jugadores/actas/')
    credencial_escolar = models.FileField(upload_to='jugadores/escolar/')
    archivo_afiliacion = models.FileField(upload_to='jugadores/afiliacion/')
    archivo_pago = models.FileField(upload_to='jugadores/pagos/', null=True, blank=True) 
    
    estado_validacion = models.CharField(max_length=20, choices=ESTADOS, default='PENDIENTE', db_index=True)
    motivo_rechazo = models.TextField(null=True, blank=True)
    intentos_registro = models.IntegerField(default=0)
    
    validado = models.BooleanField(default=False, db_index=True) 
    activo = models.BooleanField(default=True, db_index=True)
    tutor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='hijos_registrados')
    
    equipo = models.ForeignKey('Equipo', on_delete=models.SET_NULL, null=True, blank=True)
    equipo_solicitado = models.ForeignKey('Equipo', on_delete=models.SET_NULL, null=True, blank=True, related_name='solicitudes_de_ingreso')
    
    numero_afiliacion = models.CharField(max_length=25, unique=True, null=True, blank=True)
    codigo_qr = models.ImageField(upload_to='jugadores/qrs/', blank=True)

    def save(self, *args, **kwargs):
        if self.estado_validacion == 'APROBADO' and not self.numero_afiliacion:
            year = str(timezone.now().year)[-2:]
            
            if self.region:
                palabras = self.region.split()
                if len(palabras) > 1:
                    reg_ini = (palabras[0][0] + palabras[1][0]).upper()
                else:
                    reg_ini = self.region[:2].upper()
            else:
                reg_ini = "XX"
                
            club_ini = self.equipo.club[:3].upper() if self.equipo and self.equipo.club else "IND"
            
            # SOLUCIÓN HUECO 1: Evitar colisión de folios
            while True:
                codigo_unico = uuid.uuid4().hex[:4].upper()
                folio_generado = f"{year}{reg_ini}{club_ini}-{codigo_unico}"
                if not Jugador.objects.filter(numero_afiliacion=folio_generado).exists():
                    self.numero_afiliacion = folio_generado
                    break

        es_nuevo = self.pk is None
        super().save(*args, **kwargs)

        ruta_valida = reverse('validar_jugador_qr', args=[self.id])
        qr_url_esperada = f"{settings.SITE_URL}{ruta_valida}"
        if not self.codigo_qr or es_nuevo:
            qr_content = qr_url_esperada
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(qr_content)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            
            self.codigo_qr.save(f'qr_{self.curp}.png', File(buffer), save=False)
            super().save(update_fields=['codigo_qr'])

    @property
    def semaforo(self):
        sanciones_activas = self.sancion_set.filter(activa=True)
        adeudos_pendientes = self.adeudos_jugador.filter(pagado=False)
        multas_impagas = self.adeudos_jugador.filter(tipo_adeudo='MULTA', pagado=False)
        total_multas = sum(a.monto for a in multas_impagas)
        
        if multas_impagas.count() >= 3:
            return {'estatus': 'SANCIONADO', 'color': 'dark', 'icono': 'bi-lock-fill', 'mensaje': f"BLOQUEADO por {multas_impagas.count()} multas impagas. Adeudo total: ${total_multas}. Paga para liberar."}
        elif sanciones_activas.exists():
            sancion = sanciones_activas.first()
            return {'estatus': 'SUSPENDIDO', 'color': 'danger', 'icono': 'bi-exclamation-octagon-fill', 'mensaje': f"Suspendido por: {sancion.tipo}"}
        elif not self.activo:
            return {'estatus': 'INACTIVO (BAJA)', 'color': 'secondary', 'icono': 'bi-person-dash-fill', 'mensaje': "La administración ha dado de baja a este jugador."}
        elif adeudos_pendientes.exists():
            adeudo = adeudos_pendientes.first()
            return {'estatus': 'CON ADEUDOS', 'color': 'warning', 'icono': 'bi-currency-dollar', 'mensaje': f"Presenta adeudo pendiente (${adeudo.monto})."}
        elif self.estado_validacion == 'RECHAZADO':
            motivo = self.motivo_rechazo or "Documentación incompleta o incorrecta."
            return {'estatus': 'RECHAZADO', 'color': 'danger', 'icono': 'bi-x-circle-fill', 'mensaje': f"Documentos rechazados: {motivo}"}
        elif self.estado_validacion != 'APROBADO' or not self.validado:
            return {'estatus': 'EN REVISIÓN', 'color': 'warning', 'icono': 'bi-hourglass-split', 'mensaje': "Documentos en validación."}
            
        return {'estatus': 'ACTIVO Y AVALADO', 'color': 'success', 'icono': 'bi-check-circle-fill', 'mensaje': ""}

    @property
    def ligas_actuales(self):
        nombres = []
        for inscripcion in self.torneos_participados.all():
            if inscripcion.temporada and inscripcion.temporada.nombre not in nombres:
                nombres.append(inscripcion.temporada.nombre)
        if self.equipo:
            for inscripcion in self.equipo.torneos_jugados.all():
                if inscripcion.temporada and inscripcion.temporada.nombre not in nombres:
                    nombres.append(inscripcion.temporada.nombre)
        return nombres

    @property
    def torneos_activos(self):
        hoy = date.today()
        return [ins for ins in self.torneos_participados.all()
                if ins.temporada and not ins.temporada.campeon
                and ins.temporada.fecha_inicio <= hoy <= ins.temporada.fecha_fin]

    def __str__(self):
        return f"{self.nombres} {self.apellido_paterno} {self.apellido_materno or ''}".strip()

class Equipo(models.Model):
    RAMAS_EQUIPO = [
        ('Varonil', 'Varonil'),
        ('Femenil', 'Femenil'),
        ('Mixta', 'Mixta'),
    ]
    nombre = models.CharField(max_length=100, unique=True)
    club = models.CharField(max_length=100)
    entrenador = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='equipo_entrenado')
    logo = models.ImageField(upload_to='equipos/logos/', null=True, blank=True)
    max_jugadores = models.IntegerField(default=50)
    rama = models.CharField(max_length=10, choices=RAMAS_EQUIPO, default='Mixta')
    categoria = models.CharField(max_length=50, null=True, blank=True)
    
    def __str__(self): 
        return f"{self.club} - {self.nombre}"

class MiembroStaff(models.Model):
    CARGOS = [
        ('Entrenador Principal', 'Entrenador Principal'), 
        ('Asistente 1', 'Asistente 1'), 
        ('Asistente 2', 'Asistente 2'), 
        ('Asistente 3', 'Asistente 3'),
        ('Prep. Físico', 'Prep. Físico'), 
        ('Médico', 'Médico'), 
        ('Delegado', 'Delegado')
    ]
    equipo = models.ForeignKey(Equipo, on_delete=models.CASCADE, related_name='miembros_staff')
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    cargo = models.CharField(max_length=30, choices=CARGOS)
    telefono = models.CharField(max_length=15, null=True, blank=True)
    curp = models.CharField(max_length=18, null=True, blank=True)
    fecha_nacimiento = models.DateField(null=True, blank=True, verbose_name="Fecha de nacimiento")
    foto = models.ImageField(upload_to='staff/', null=True, blank=True)
    folio_afiliacion = models.CharField(max_length=20, unique=True, blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.folio_afiliacion:
            year = str(timezone.now().year)[-2:]
            iniciales = self.equipo.club[:2].upper() if self.equipo.club else "XX"
            # SOLUCIÓN HUECO 1: Evitar colisión de folios de staff
            while True:
                codigo_unico = uuid.uuid4().hex[:4].upper()
                folio_gen = f"{year}E{iniciales}-{codigo_unico}"
                if not MiembroStaff.objects.filter(folio_afiliacion=folio_gen).exists():
                    self.folio_afiliacion = folio_gen
                    break
        super().save(*args, **kwargs)

class HistorialEquipo(models.Model):
    jugador = models.ForeignKey(Jugador, on_delete=models.CASCADE, related_name='historial_equipos')
    equipo = models.ForeignKey(Equipo, on_delete=models.CASCADE)
    fecha_registro = models.DateTimeField(auto_now_add=True)
    fecha_salida = models.DateTimeField(null=True, blank=True)
    motivo = models.CharField(max_length=100, default="Ingreso")

class PerfilTutor(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    telefono = models.CharField(max_length=15, null=True, blank=True)

class PerfilEntrenador(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil_entrenador')
    foto = models.ImageField(upload_to='entrenadores/fotos/', null=True, blank=True)
    telefono = models.CharField(max_length=15, null=True, blank=True)
    curp = models.CharField(max_length=18, null=True, blank=True)
    fecha_nacimiento = models.DateField(null=True, blank=True, verbose_name="Fecha de nacimiento")

class Temporada(models.Model):
    RAMAS = [
        ('Varonil', 'Varonil'), 
        ('Femenil', 'Femenil'), 
        ('Mixta', 'Mixta')
    ]
    nombre = models.CharField(max_length=100)
    rama = models.CharField(max_length=10, choices=RAMAS, default='Mixta')
    anio_nac_min = models.IntegerField(null=True, blank=True)
    anio_nac_max = models.IntegerField(null=True, blank=True)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    costo_inscripcion = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    
    # SOLUCIÓN HUECO 4: Flexibilidad para configurar reglas desde el panel
    min_jugadores_roster = models.IntegerField(default=8)
    max_jugadores_roster = models.IntegerField(default=15)
    
    inscripciones_abiertas = models.BooleanField(default=False)
    dias_tolerancia_pago = models.IntegerField(default=15)
    region = models.CharField(max_length=50, choices=REGIONES + [('Cualquier Región', 'Cualquier Región')], default='Cualquier Región')
    
    campeon = models.ForeignKey('Equipo', on_delete=models.SET_NULL, null=True, blank=True, related_name='campeonatos')
    
    @property
    def estado_actual(self):
        if self.campeon:
            return 'Finalizada'
        hoy = timezone.now().date()
        if hoy < self.fecha_inicio:
            return 'Inscripciones Cerradas (Próximo)' if not self.inscripciones_abiertas else 'Próximo Torneo'
        if self.inscripciones_abiertas and hoy <= self.fecha_fin:
            return 'Inscripciones Abiertas'
        if hoy <= self.fecha_fin:
            return 'En Curso'
        return 'Por Finalizar (Sin Campeón)'

    @property
    def fecha_limite_pago(self):
        from datetime import timedelta
        return self.fecha_inicio + timedelta(days=self.dias_tolerancia_pago)

class InscripcionTorneo(models.Model):
    temporada = models.ForeignKey(Temporada, on_delete=models.CASCADE, related_name='inscripciones')
    equipo = models.ForeignKey(Equipo, on_delete=models.CASCADE, related_name='torneos_jugados')
    jugadores = models.ManyToManyField(Jugador, related_name='torneos_participados')
    fecha_inscripcion = models.DateTimeField(auto_now_add=True)
    validada = models.BooleanField(default=False)

    class Meta:
        unique_together = ('temporada', 'equipo')

class Adeudo(models.Model):
    TIPOS_ADEUDO = [
        ('INSCRIPCION', 'Inscripción a Torneo'),
        ('CREDENTIAL', 'Credenciales / Trámites'),
        ('MULTA', 'Multas / Disciplina'),
        ('ARBITRAJE', 'Arbitraje')
    ]
    
    ESTADOS_PAGO = [
        ('PENDIENTE', 'Pendiente de Pago'),
        ('REVISION', 'En Revisión (Voucher Enviado)'),
        ('PAGADO', 'Liquidado / Pagado')
    ]

    equipo = models.ForeignKey(Equipo, on_delete=models.CASCADE, null=True, blank=True)
    tutor = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='adeudos_tutor')
    jugador = models.ForeignKey(Jugador, on_delete=models.SET_NULL, null=True, blank=True, related_name='adeudos_jugador')
    temporada = models.ForeignKey(Temporada, on_delete=models.SET_NULL, null=True, blank=True, related_name='adeudos_temporada')
    
    concepto = models.CharField(max_length=200)
    monto = models.DecimalField(max_digits=8, decimal_places=2)
    tipo_adeudo = models.CharField(max_length=20, choices=TIPOS_ADEUDO, default='INSCRIPCION', db_index=True)
    estado = models.CharField(max_length=20, choices=ESTADOS_PAGO, default='PENDIENTE', db_index=True)
    
    voucher_comprobante = models.FileField(upload_to='vouchers_finanzas/', null=True, blank=True)
    pagado = models.BooleanField(default=False, db_index=True)
    sancion = models.ForeignKey('Sancion', on_delete=models.SET_NULL, null=True, blank=True, related_name='adeudos')
    
    fecha_creacion = models.DateTimeField(auto_now_add=True, db_index=True)
    fecha_pago = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.estado == 'PAGADO':
            self.pagado = True
            if not self.fecha_pago:
                self.fecha_pago = timezone.now()
        else:
            self.pagado = False
        super().save(*args, **kwargs)

    def __str__(self):
        entidad = self.equipo.club if self.equipo else (self.jugador.nombres if self.jugador else "General")
        return f"{self.concepto} - {entidad} (${self.monto})"

class SolicitudCambioEquipo(models.Model):
    ESTADOS_CAMBIO = [
        ('PENDIENTE', 'Pendiente'),
        ('APROBADO', 'Aprobado'),
        ('RECHAZADO', 'Rechazado')
    ]
    jugador = models.ForeignKey(Jugador, on_delete=models.CASCADE, related_name='solicitudes_cambio')
    equipo_origen = models.ForeignKey(Equipo, on_delete=models.CASCADE, related_name='salidas_solicitadas', null=True, blank=True)
    equipo_destino = models.ForeignKey(Equipo, on_delete=models.CASCADE, related_name='ingresos_solicitados')
    estado = models.CharField(max_length=20, choices=ESTADOS_CAMBIO, default='PENDIENTE', db_index=True)
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    fecha_resolucion = models.DateTimeField(null=True, blank=True)

class Partido(models.Model):
    temporada = models.ForeignKey(Temporada, on_delete=models.CASCADE, related_name='partidos')
    equipo_local = models.ForeignKey(Equipo, on_delete=models.CASCADE, related_name='partidos_local')
    equipo_visitante = models.ForeignKey(Equipo, on_delete=models.CASCADE, related_name='partidos_visitante')
    puntos_local = models.IntegerField(default=0)
    puntos_visitante = models.IntegerField(default=0)
    fecha_hora = models.DateTimeField(null=True, blank=True)
    cancha = models.CharField(max_length=100, null=True, blank=True)
    jornada = models.CharField(max_length=50, null=True, blank=True)
    jugado = models.BooleanField(default=False, db_index=True)

    @property
    def ganador(self):
        if not self.jugado:
            return None
        if self.puntos_local > self.puntos_visitante:
            return self.equipo_local
        elif self.puntos_visitante > self.puntos_local:
            return self.equipo_visitante
        return None

class Sancion(models.Model):
    TIPOS = [
        ('Técnica', 'Falta Técnica'), 
        ('Antideportiva', 'Falta Antideportiva'), 
        ('Expulsión', 'Expulsión'), 
        ('Suspensión LGE', 'Suspensión por Liga')
    ]
    temporada = models.ForeignKey(Temporada, on_delete=models.CASCADE)
    jugador = models.ForeignKey(Jugador, on_delete=models.SET_NULL, null=True, blank=True)
    entrenador = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    tipo = models.CharField(max_length=50, choices=TIPOS)
    motivo = models.TextField()
    juegos_suspension = models.IntegerField(default=0)
    juegos_cumplidos = models.IntegerField(default=0)
    fecha_sancion = models.DateTimeField(auto_now_add=True)
    activa = models.BooleanField(default=True, db_index=True)
    monto_multa = models.DecimalField(max_digits=8, decimal_places=2, default=250.00)
    pagada = models.BooleanField(default=False)
    fecha_pago = models.DateTimeField(null=True, blank=True)


class ConfiguracionSistema(models.Model):
    inscripciones_abiertas = models.BooleanField(default=False, verbose_name="Inscripciones globales abiertas")
    fecha_inicio_inscripciones = models.DateField(null=True, blank=True, verbose_name="Fecha inicio inscripciones")
    fecha_fin_inscripciones = models.DateField(null=True, blank=True, verbose_name="Fecha fin inscripciones")
    monto_sancion_default = models.DecimalField(max_digits=8, decimal_places=2, default=250.00, verbose_name="Monto multa por defecto")
    costo_inscripcion = models.DecimalField(max_digits=8, decimal_places=2, default=0.00, verbose_name="Costo de inscripción general")
    numero_cuenta = models.CharField(max_length=20, blank=True, null=True, verbose_name="Número de cuenta bancaria")
    banco = models.CharField(max_length=100, blank=True, null=True, verbose_name="Nombre del banco")
    nombre_cuenta = models.CharField(max_length=200, blank=True, null=True, verbose_name="Titular de la cuenta")

    class Meta:
        verbose_name = "Configuración del Sistema"
        verbose_name_plural = "Configuración del Sistema"

    @property
    def inscripciones_activas(self):
        from datetime import date
        hoy = date.today()
        if not self.inscripciones_abiertas:
            return False
        if self.fecha_inicio_inscripciones and hoy < self.fecha_inicio_inscripciones:
            return False
        if self.fecha_fin_inscripciones and hoy > self.fecha_fin_inscripciones:
            return False
        return True

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("La configuración del sistema no puede eliminarse.")

    def __str__(self):
        return "Configuración Global del Sistema"


class SolicitudCambioContrasena(models.Model):
    ESTADOS = [
        ('PENDIENTE', 'Pendiente'),
        ('APROBADA', 'Aprobada'),
        ('RECHAZADA', 'Rechazada'),
    ]
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='solicitudes_contrasena')
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='PENDIENTE')
    contrasena_temporal = models.CharField(max_length=128, null=True, blank=True)
    motivo_rechazo = models.TextField(null=True, blank=True, verbose_name="Motivo de rechazo")

    class Meta:
        verbose_name = "Solicitud de Cambio de Contraseña"
        verbose_name_plural = "Solicitudes de Cambio de Contraseña"
        ordering = ['-fecha_solicitud']

    def __str__(self):
        return f"{self.usuario.username} - {self.get_estado_display()}"


# ==============================================================================
# SOLUCIÓN HUECO 2: SEÑALES (SIGNALS) PARA PREVENIR BLOAT DE ALMACENAMIENTO
# ==============================================================================

def borrar_archivo_fisico(campo_archivo):
    """Utilidad para borrar el archivo físico del disco duro."""
    if campo_archivo and hasattr(campo_archivo, 'path') and os.path.isfile(campo_archivo.path):
        try:
            os.remove(campo_archivo.path)
        except Exception:
            pass # Prevenir caídas si el archivo está bloqueado por el SO

# Al Eliminar Registros Completos
@receiver(post_delete, sender=Jugador)
def eliminar_archivos_jugador(sender, instance, **kwargs):
    campos = [instance.foto_perfil, instance.archivo_curp, instance.archivo_identificacion, 
              instance.acta_nacimiento, instance.credencial_escolar, instance.archivo_afiliacion, 
              instance.archivo_pago, instance.codigo_qr]
    for campo in campos: borrar_archivo_fisico(campo)

@receiver(post_delete, sender=Equipo)
def eliminar_logo_equipo(sender, instance, **kwargs):
    borrar_archivo_fisico(instance.logo)

@receiver(post_delete, sender=MiembroStaff)
def eliminar_foto_staff(sender, instance, **kwargs):
    borrar_archivo_fisico(instance.foto)

@receiver(post_delete, sender=Adeudo)
def eliminar_voucher_adeudo(sender, instance, **kwargs):
    borrar_archivo_fisico(instance.voucher_comprobante)

# Al Actualizar Archivos (Borrar el viejo para no dejar basura)
@receiver(pre_save, sender=Jugador)
def auto_eliminar_archivos_viejos_jugador(sender, instance, **kwargs):
    if not instance.pk: return
    try: old_instance = Jugador.objects.get(pk=instance.pk)
    except Jugador.DoesNotExist: return
    
    campos = ['foto_perfil', 'archivo_curp', 'archivo_identificacion', 'acta_nacimiento', 
              'credencial_escolar', 'archivo_afiliacion', 'archivo_pago', 'codigo_qr']
    for campo in campos:
        old_file = getattr(old_instance, campo)
        new_file = getattr(instance, campo)
        if old_file and new_file and old_file != new_file:
            borrar_archivo_fisico(old_file)