import re
import os
from datetime import date
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django.db.models import Q, Count
from django.core.exceptions import ValidationError
from .models import Jugador, MiembroStaff, PerfilTutor, PerfilEntrenador, Equipo, Adeudo, Temporada, InscripcionTorneo, Partido, Sancion, SolicitudCambioEquipo, ConfiguracionSistema, SolicitudCambioContrasena

def validar_archivo_estricto(archivo):
    ext_permitidas = ['.pdf', '.jpg', '.jpeg', '.png']
    ext = os.path.splitext(archivo.name)[1].lower()
    if ext not in ext_permitidas:
        raise ValidationError(f"Formato '{ext}' no permitido. Solo se admite PDF o imágenes (JPG, PNG).")
    if archivo.size > 5242880:
        raise ValidationError("El archivo es demasiado pesado. El límite máximo es de 5MB.")

def validar_solo_imagen(archivo):
    ext_permitidas = ['.jpg', '.jpeg', '.png']
    ext = os.path.splitext(archivo.name)[1].lower()
    if ext not in ext_permitidas:
        raise ValidationError("Para la foto de perfil solo se admiten imágenes (JPG, JPEG, PNG).")
    if archivo.size > 5242880:
        raise ValidationError("La foto es demasiado pesada. El límite máximo es de 5MB.")

class RegistroTutorForm(UserCreationForm):
    first_name = forms.CharField(max_length=30, required=True, label="Nombre(s)", widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tu nombre(s)'}))
    last_name = forms.CharField(max_length=30, required=True, label="Apellidos", widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tus apellidos'}))
    email = forms.EmailField(required=True, label="Correo Electrónico", widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'correo@ejemplo.com'}))
    
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Elige un nombre de usuario'})
        self.fields['username'].help_text = 'Máximo 20 caracteres. Solo letras y números.'
        self.fields['password1'].widget.attrs.update({'class': 'form-control', 'placeholder': '••••••••'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Repite la contraseña'})
        self.fields['password1'].help_text = 'Mínimo 8 caracteres. Al menos una mayúscula y un número.'

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if not username:
            raise forms.ValidationError("Este campo es obligatorio.")
        if len(username) > 20:
            raise forms.ValidationError("El nombre de usuario debe tener máximo 20 caracteres.")
        if not re.match(r'^[a-zA-Z0-9]+$', username):
            raise forms.ValidationError("Solo se permiten letras y números, sin espacios ni caracteres especiales.")
        return username

    def clean_first_name(self):
        nombre = self.cleaned_data.get('first_name')
        if not nombre:
            raise forms.ValidationError("Este campo es obligatorio.")
        if len(nombre) > 30:
            raise forms.ValidationError("El nombre debe tener máximo 30 caracteres.")
        if not re.match(r'^[a-zA-ZáéíóúüñÑÁÉÍÓÚÜ\s]+$', nombre):
            raise forms.ValidationError("Solo se permiten letras y espacios.")
        return nombre

    def clean_last_name(self):
        apellido = self.cleaned_data.get('last_name')
        if not apellido:
            raise forms.ValidationError("Este campo es obligatorio.")
        if len(apellido) > 30:
            raise forms.ValidationError("Los apellidos deben tener máximo 30 caracteres.")
        if not re.match(r'^[a-zA-ZáéíóúüñÑÁÉÍÓÚÜ\s]+$', apellido):
            raise forms.ValidationError("Solo se permiten letras y espacios.")
        return apellido

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not email:
            raise forms.ValidationError("Este campo es obligatorio.")
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Este correo electrónico ya está registrado en el sistema.")
        return email

    def clean_password1(self):
        password = self.cleaned_data.get('password1')
        if not password:
            raise forms.ValidationError("Este campo es obligatorio.")
        if len(password) < 8:
            raise forms.ValidationError("La contraseña debe tener al menos 8 caracteres.")
        if len(password) > 128:
            raise forms.ValidationError("La contraseña debe tener máximo 128 caracteres.")
        if not re.search(r'[A-Z]', password):
            raise forms.ValidationError("La contraseña debe contener al menos una letra mayúscula.")
        if not re.search(r'[0-9]', password):
            raise forms.ValidationError("La contraseña debe contener al menos un número.")
        return password

class JugadorForm(forms.ModelForm):
    class Meta:
        model = Jugador
        fields = [
            'nombres', 'apellido_paterno', 'apellido_materno', 'curp', 
            'rama', 'numero_camiseta', 'posicion', 
            'tipo_sangre', 'region', 'municipio_vive', 'telefono_credencial', 
            'foto_perfil', 'archivo_curp', 
            'archivo_identificacion', 'acta_nacimiento', 'credencial_escolar',
            'archivo_afiliacion'
        ]
        widgets = {
            'nombres': forms.TextInput(attrs={'class': 'form-control'}),
            'apellido_paterno': forms.TextInput(attrs={'class': 'form-control'}),
            'apellido_materno': forms.TextInput(attrs={'class': 'form-control'}),
            'curp': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. ABCD123456EFGHIJ78'}),
            'rama': forms.Select(attrs={'class': 'form-select'}),
            'numero_camiseta': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. 23'}),
            'posicion': forms.Select(attrs={'class': 'form-select'}),
            'tipo_sangre': forms.Select(attrs={'class': 'form-select'}),
            'region': forms.Select(attrs={'class': 'form-select'}),
            'municipio_vive': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Municipio de residencia'}),
            'telefono_credencial': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 10, 'placeholder': '10 dígitos'}),
            'foto_perfil': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'archivo_curp': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf, image/*'}),
            'archivo_identificacion': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf, image/*'}),
            'acta_nacimiento': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf, image/*'}),
            'credencial_escolar': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf, image/*'}),
            'archivo_afiliacion': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf, image/*'}),
        }

    def clean_foto_perfil(self):
        f = self.cleaned_data.get('foto_perfil')
        if f: validar_solo_imagen(f)
        return f

    def clean_archivo_curp(self):
        f = self.cleaned_data.get('archivo_curp')
        if f: validar_archivo_estricto(f)
        return f

    def clean_archivo_identificacion(self):
        f = self.cleaned_data.get('archivo_identificacion')
        if f: validar_archivo_estricto(f)
        return f

    def clean_acta_nacimiento(self):
        f = self.cleaned_data.get('acta_nacimiento')
        if f: validar_archivo_estricto(f)
        return f

    def clean_credencial_escolar(self):
        f = self.cleaned_data.get('credencial_escolar')
        if f: validar_archivo_estricto(f)
        return f

    def clean_archivo_afiliacion(self):
        f = self.cleaned_data.get('archivo_afiliacion')
        if f: validar_archivo_estricto(f)
        return f

    def clean_curp(self):
        curp = self.cleaned_data.get('curp')
        if not curp:
            raise ValidationError("La CURP es obligatoria.")
        curp = curp.upper()
        curp_regex = r'^[A-Z]{4}[0-9]{6}[A-Z]{6}[0-9A-Z]{2}$'
        
        if not re.match(curp_regex, curp): 
            raise ValidationError("La CURP no tiene un formato válido (Deben ser 18 caracteres exactos).")
            
        fecha_str = curp[4:10]
        try:
            anio = int(fecha_str[0:2])
            anio = anio + 2000 if anio <= date.today().year % 100 else anio + 1900
            fecha_nac = date(anio, int(fecha_str[2:4]), int(fecha_str[4:6]))
        except ValueError:
            raise ValidationError("La fecha incrustada en la CURP es inválida.")
            
        edad_deportiva = date.today().year - fecha_nac.year
        
        if edad_deportiva >= 18: 
            raise ValidationError(f"El jugador supera el límite de edad ({edad_deportiva} años). Debe ser estrictamente menor a 18 años.")
        if edad_deportiva < 6:
            raise ValidationError(f"El jugador no cumple la edad mínima de 6 años.")
            
        self.instance.fecha_nacimiento = fecha_nac
        return curp

class HijoForm(JugadorForm):
    pass

class SolicitudCambioForm(forms.ModelForm):
    class Meta:
        model = SolicitudCambioEquipo
        fields = ['equipo_destino']
        widgets = {'equipo_destino': forms.Select(attrs={'class': 'form-select', 'required': True})}

class RegistroEntrenadorForm(forms.Form):
    username = forms.CharField(max_length=20, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre de usuario'}), help_text='Máximo 20 caracteres. Solo letras y números.')
    first_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre(s)'}))
    last_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Apellidos'}))
    password = forms.CharField(max_length=128, required=True, widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': '••••••••'}), label='Contraseña')
    password_confirm = forms.CharField(max_length=128, required=True, widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Repite la contraseña'}), label='Confirmar contraseña')

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if not re.match(r'^[a-zA-Z0-9]+$', username):
            raise forms.ValidationError("Solo se permiten letras y números.")
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Ese nombre de usuario ya está en uso.")
        return username

    def clean_password(self):
        password = self.cleaned_data.get('password')
        if len(password) < 8:
            raise forms.ValidationError("La contraseña debe tener al menos 8 caracteres.")
        if not re.search(r'[A-Z]', password):
            raise forms.ValidationError("La contraseña debe contener al menos una letra mayúscula.")
        if not re.search(r'[0-9]', password):
            raise forms.ValidationError("La contraseña debe contener al menos un número.")
        return password

    def clean_first_name(self):
        nombre = self.cleaned_data.get('first_name')
        if not re.match(r'^[a-zA-ZáéíóúñÑÁÉÍÓÚ\s]+$', nombre):
            raise forms.ValidationError("Solo se permiten letras.")
        return nombre

    def clean_last_name(self):
        apellido = self.cleaned_data.get('last_name')
        if not re.match(r'^[a-zA-ZáéíóúñÑÁÉÍÓÚ\s]+$', apellido):
            raise forms.ValidationError("Solo se permiten letras.")
        return apellido

    def clean(self):
        cd = super().clean()
        if cd.get('password') and cd.get('password_confirm') and cd['password'] != cd['password_confirm']:
            raise forms.ValidationError("Las contraseñas no coinciden.")
        return cd

    def save(self):
        user = User(
            username=self.cleaned_data['username'],
            first_name=self.cleaned_data['first_name'],
            last_name=self.cleaned_data['last_name'],
        )
        user.set_password(self.cleaned_data['password'])
        user.save()
        return user

def validar_curp_adulto(curp, instance, required=True):
    if not curp:
        if required:
            raise ValidationError("La CURP es obligatoria.")
        return curp
    curp = curp.upper()
    curp_regex = r'^[A-Z]{4}[0-9]{6}[A-Z]{6}[0-9A-Z]{2}$'
    if not re.match(curp_regex, curp):
        raise ValidationError("La CURP no tiene un formato válido (Deben ser 18 caracteres exactos).")
    fecha_str = curp[4:10]
    try:
        anio = int(fecha_str[0:2])
        anio = anio + 2000 if anio <= date.today().year % 100 else anio + 1900
        fecha_nac = date(anio, int(fecha_str[2:4]), int(fecha_str[4:6]))
    except ValueError:
        raise ValidationError("La fecha incrustada en la CURP es inválida.")
    edad = date.today().year - fecha_nac.year
    if edad < 18:
        raise ValidationError(f"La persona debe ser mayor de edad (tiene {edad} años según la CURP).")
    instance.fecha_nacimiento = fecha_nac
    return curp

def validar_telefono(telefono):
    if not telefono:
        return telefono
    solo_digitos = re.sub(r'\D', '', telefono)
    if len(solo_digitos) != 10:
        raise ValidationError("El teléfono debe tener exactamente 10 dígitos.")
    return solo_digitos

class MiembroStaffForm(forms.ModelForm):
    class Meta:
        model = MiembroStaff
        fields = ['nombres', 'apellidos', 'cargo', 'telefono', 'curp', 'foto']
        widgets = {
            'nombres': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 100}),
            'apellidos': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 100}),
            'cargo': forms.Select(attrs={'class': 'form-select'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 10, 'placeholder': '10 dígitos'}),
            'curp': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 18, 'placeholder': 'Ej. ABCD123456EFGHIJ78'}),
            'foto': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def clean_telefono(self):
        return validar_telefono(self.cleaned_data.get('telefono'))

    def clean_curp(self):
        return validar_curp_adulto(self.cleaned_data.get('curp'), self.instance, required=False)

    def clean_foto(self):
        f = self.cleaned_data.get('foto')
        if f: validar_solo_imagen(f)
        return f

class EquipoForm(forms.ModelForm):
    class Meta:
        model = Equipo
        fields = ['nombre', 'club', 'rama', 'categoria', 'max_jugadores', 'entrenador', 'logo'] 
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'club': forms.TextInput(attrs={'class': 'form-control'}),
            'rama': forms.Select(attrs={'class': 'form-select'}),
            'categoria': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Infantil, Juvenil, Libre'}),
            'max_jugadores': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'entrenador': forms.Select(attrs={'class': 'form-select'}),
            'logo': forms.FileInput(attrs={'class': 'form-control'}),
        }

    def clean_logo(self):
        f = self.cleaned_data.get('logo')
        if f: validar_solo_imagen(f)
        return f
    
    def __init__(self, *args, **kwargs):
        super(EquipoForm, self).__init__(*args, **kwargs)
        equipo_id = self.instance.id if self.instance and self.instance.id else None
        base_qs = User.objects.filter(is_staff=False, perfil__isnull=True)
        if equipo_id and self.instance.entrenador:
            self.fields['entrenador'].queryset = base_qs.filter(
                Q(equipo_entrenado__isnull=True) | Q(id=self.instance.entrenador.id)
            ).distinct().order_by('first_name')
        else:
            self.fields['entrenador'].queryset = base_qs.filter(equipo_entrenado__isnull=True).order_by('first_name')
        self.fields['entrenador'].empty_label = "--- Selecciona un Entrenador Libre ---"
        self.fields['max_jugadores'].initial = 50

    def clean_nombre(self):
        nombre = self.cleaned_data.get('nombre')
        if not nombre:
            raise forms.ValidationError("Este campo es obligatorio.")
        qs = Equipo.objects.filter(nombre__iexact=nombre)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya existe un equipo con este nombre. Por favor elige otro.")
        return nombre

class AdeudoForm(forms.ModelForm):
    class Meta:
        model = Adeudo
        fields = ['equipo', 'jugador', 'concepto', 'monto', 'tipo_adeudo']
        widgets = {
            'equipo': forms.Select(attrs={'class': 'form-select'}),
            'jugador': forms.Select(attrs={'class': 'form-select'}),
            'concepto': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 200}),
            'monto': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tipo_adeudo': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super(AdeudoForm, self).__init__(*args, **kwargs)
        self.fields['equipo'].required = False
        self.fields['jugador'].required = False

    def clean(self):
        cleaned_data = super().clean()
        equipo = cleaned_data.get('equipo')
        jugador = cleaned_data.get('jugador')
        if not equipo and not jugador:
            raise ValidationError("Debes asignar al menos un equipo o un jugador al adeudo.")
        return cleaned_data

class VoucherForm(forms.ModelForm):
    class Meta:
        model = Adeudo
        fields = ['voucher_comprobante']
        widgets = {
            'voucher_comprobante': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*,.pdf'})
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['voucher_comprobante'].required = True
        self.fields['voucher_comprobante'].error_messages = {'required': 'Debes seleccionar un archivo o fotografía antes de enviar el comprobante.'}

    def clean_voucher_comprobante(self):
        f = self.cleaned_data.get('voucher_comprobante')
        if f: validar_archivo_estricto(f)
        return f

class TemporadaForm(forms.ModelForm):
    class Meta:
        model = Temporada
        fields = ['nombre', 'rama', 'region', 'anio_nac_min', 'anio_nac_max', 'fecha_inicio', 'fecha_fin', 'costo_inscripcion', 'min_jugadores_roster', 'max_jugadores_roster', 'inscripciones_abiertas', 'dias_tolerancia_pago']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'rama': forms.Select(attrs={'class': 'form-select'}),
            'region': forms.Select(attrs={'class': 'form-select'}),
            'anio_nac_min': forms.NumberInput(attrs={'class': 'form-control'}),
            'anio_nac_max': forms.NumberInput(attrs={'class': 'form-control'}),
            'fecha_inicio': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_fin': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'costo_inscripcion': forms.NumberInput(attrs={'class': 'form-control'}),
            'min_jugadores_roster': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_jugadores_roster': forms.NumberInput(attrs={'class': 'form-control'}),
            'inscripciones_abiertas': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'dias_tolerancia_pago': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        }

class TemporadaEditForm(forms.ModelForm):
    class Meta:
        model = Temporada
        fields = ['nombre', 'rama', 'region', 'anio_nac_min', 'anio_nac_max', 'costo_inscripcion', 'min_jugadores_roster', 'max_jugadores_roster', 'inscripciones_abiertas', 'dias_tolerancia_pago']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'rama': forms.Select(attrs={'class': 'form-select'}),
            'region': forms.Select(attrs={'class': 'form-select'}),
            'anio_nac_min': forms.NumberInput(attrs={'class': 'form-control'}),
            'anio_nac_max': forms.NumberInput(attrs={'class': 'form-control'}),
            'costo_inscripcion': forms.NumberInput(attrs={'class': 'form-control'}),
            'min_jugadores_roster': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_jugadores_roster': forms.NumberInput(attrs={'class': 'form-control'}),
            'inscripciones_abiertas': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'dias_tolerancia_pago': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        }

class RosterForm(forms.ModelForm):
    class Meta:
        model = InscripcionTorneo
        fields = ['jugadores']
        widgets = {'jugadores': forms.CheckboxSelectMultiple()}
        
    def __init__(self, *args, **kwargs):
        equipo = kwargs.pop('equipo', None)
        self.temporada = kwargs.pop('temporada', None)
        super(RosterForm, self).__init__(*args, **kwargs)
        
        if equipo and self.temporada:
            qs = Jugador.objects.filter(equipo=equipo, activo=True, validado=True).prefetch_related('torneos_participados__temporada')
            if self.temporada.anio_nac_min:
                qs = qs.filter(fecha_nacimiento__year__gte=self.temporada.anio_nac_min)
            if self.temporada.anio_nac_max:
                qs = qs.filter(fecha_nacimiento__year__lte=self.temporada.anio_nac_max)
            if self.temporada.rama != 'Mixta':
                qs = qs.filter(rama=self.temporada.rama)
            if self.temporada.region != 'Cualquier Región':
                qs = qs.filter(region=self.temporada.region)
            # Excluir SUSPENDIDO (sanción activa) y SANCIONADO (≥3 multas impagas)
            qs = qs.exclude(sancion__activa=True)
            qs = qs.annotate(
                multas_count=Count('adeudos_jugador', filter=Q(adeudos_jugador__tipo_adeudo='MULTA', adeudos_jugador__pagado=False))
            ).filter(multas_count__lt=3).distinct()
            self.fields['jugadores'].queryset = qs.order_by('nombres')
            self.fields['jugadores'].label_from_instance = lambda obj: f"{obj.nombres} {obj.apellido_paterno} | Juega en: {', '.join([t.temporada.nombre for t in obj.torneos_participados.all()]) if obj.torneos_participados.exists() else 'Ningún torneo aún'}"

    def clean_jugadores(self):
        jugadores = self.cleaned_data.get('jugadores')
        if not self.temporada: return jugadores

        for j in jugadores:
            if j.fecha_nacimiento:
                if self.temporada.anio_nac_min and j.fecha_nacimiento.year < self.temporada.anio_nac_min:
                    raise ValidationError(f"Seguridad: El jugador {j.nombres} excede la edad permitida del torneo.")
                if self.temporada.anio_nac_max and j.fecha_nacimiento.year > self.temporada.anio_nac_max:
                    raise ValidationError(f"Seguridad: El jugador {j.nombres} no cumple la edad mínima del torneo.")
            if self.temporada.rama != 'Mixta' and j.rama != self.temporada.rama:
                raise ValidationError(f"Seguridad: El jugador {j.nombres} pertenece a otra rama.")
            if self.temporada.region != 'Cualquier Región' and j.region != self.temporada.region:
                raise ValidationError(f"Seguridad: El jugador {j.nombres} no pertenece a la región {self.temporada.region}.")
            multas_impagas = j.adeudos_jugador.filter(tipo_adeudo='MULTA', pagado=False).count()
            if multas_impagas >= 3:
                raise ValidationError(f"Bloqueado: {j.nombres} tiene {multas_impagas} multas impagas (SANCIONADO).")
            if j.sancion_set.filter(activa=True).exists():
                raise ValidationError(f"Bloqueado: {j.nombres} tiene una suspensión activa (SUSPENDIDO).")
                
        return jugadores

class PartidoForm(forms.ModelForm):
    class Meta:
        model = Partido
        fields = ['jornada', 'equipo_local', 'equipo_visitante', 'fecha_hora', 'cancha']
        widgets = {
            'fecha_hora': forms.DateTimeInput(attrs={'type': 'datetime-local', 'class': 'form-control'}),
            'jornada': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Jornada 1'}),
            'cancha': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Cancha Principal'}),
            'equipo_local': forms.Select(attrs={'class': 'form-select'}),
            'equipo_visitante': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        local = cleaned_data.get('equipo_local')
        visitante = cleaned_data.get('equipo_visitante')
        if local and visitante and local == visitante:
            raise ValidationError("El equipo local y visitante no pueden ser el mismo equipo.")
        return cleaned_data

class ResultadoForm(forms.ModelForm):
    class Meta:
        model = Partido
        fields = ['puntos_local', 'puntos_visitante', 'jugado']
        widgets = {
            'puntos_local': forms.NumberInput(attrs={'class': 'form-control form-control-lg text-center fw-bold'}),
            'puntos_visitante': forms.NumberInput(attrs={'class': 'form-control form-control-lg text-center fw-bold'}),
            'jugado': forms.CheckboxInput(attrs={'class': 'form-check-input mt-2', 'style': 'transform: scale(1.5);'}),
        }

class SancionForm(forms.ModelForm):
    monto_multa = forms.DecimalField(
        max_digits=8, decimal_places=2, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        label="Monto de la multa ($)"
    )

    class Meta:
        model = Sancion
        fields = ['jugador', 'entrenador', 'tipo', 'juegos_suspension', 'motivo', 'monto_multa']
        widgets = {
            'jugador': forms.Select(attrs={'class': 'form-select'}),
            'entrenador': forms.Select(attrs={'class': 'form-select'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'juegos_suspension': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'motivo': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['entrenador'].queryset = User.objects.filter(is_staff=False, perfil__isnull=True).order_by('first_name', 'username')
        try:
            config = ConfiguracionSistema.objects.get(pk=1)
            self.fields['monto_multa'].initial = config.monto_sancion_default
        except ConfiguracionSistema.DoesNotExist:
            self.fields['monto_multa'].initial = 250.00


class ConfiguracionSistemaForm(forms.ModelForm):
    class Meta:
        model = ConfiguracionSistema
        fields = ['inscripciones_abiertas', 'fecha_inicio_inscripciones', 'fecha_fin_inscripciones', 'monto_sancion_default', 'costo_inscripcion', 'numero_cuenta', 'banco', 'nombre_cuenta']
        widgets = {
            'inscripciones_abiertas': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'fecha_inicio_inscripciones': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_fin_inscripciones': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'monto_sancion_default': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'costo_inscripcion': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'numero_cuenta': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 20, 'placeholder': 'Ej. 1234-5678-9012-3456'}),
            'banco': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 100, 'placeholder': 'Ej. BBVA, Santander...'}),
            'nombre_cuenta': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 200, 'placeholder': 'Nombre del titular'}),
        }
        labels = {
            'inscripciones_abiertas': '¿Inscripciones globales abiertas?',
            'fecha_inicio_inscripciones': 'Fecha de inicio de inscripciones',
            'fecha_fin_inscripciones': 'Fecha de cierre de inscripciones',
            'monto_sancion_default': 'Monto de multa por defecto ($)',
            'costo_inscripcion': 'Costo de inscripción general ($)',
            'numero_cuenta': 'Número de cuenta bancaria',
            'banco': 'Nombre del banco',
            'nombre_cuenta': 'Titular de la cuenta',
        }


class EntrenadorPerfilForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30, required=True, label='Nombre(s)', widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=30, required=True, label='Apellido(s)', widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(required=False, label='Correo electrónico', widget=forms.EmailInput(attrs={'class': 'form-control'}))

    class Meta:
        model = PerfilEntrenador
        fields = ['foto', 'telefono', 'curp']
        widgets = {
            'foto': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 10, 'placeholder': '10 dígitos'}),
            'curp': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 18, 'placeholder': 'Ej. ABCD123456EFGHIJ78'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if self.user:
            self.fields['first_name'].initial = self.user.first_name
            self.fields['last_name'].initial = self.user.last_name
            self.fields['email'].initial = self.user.email

    def clean_telefono(self):
        return validar_telefono(self.cleaned_data.get('telefono'))

    def clean_curp(self):
        return validar_curp_adulto(self.cleaned_data.get('curp'), self.instance, required=False)

    def clean_foto(self):
        foto = self.cleaned_data.get('foto')
        if foto:
            if foto.size > 5 * 1024 * 1024:
                raise ValidationError('La imagen no puede superar los 5 MB.')
            ext = os.path.splitext(foto.name)[1].lower()
            if ext not in ('.jpg', '.jpeg', '.png', '.webp'):
                raise ValidationError('Solo se permiten imágenes JPG, PNG o WebP.')
        return foto

    def save(self, commit=True):
        perfil = super().save(commit=False)
        if self.user:
            self.user.first_name = self.cleaned_data['first_name']
            self.user.last_name = self.cleaned_data['last_name']
            self.user.email = self.cleaned_data['email']
            if commit:
                self.user.save()
        if commit:
            perfil.save()
        return perfil

class ResetPasswordForm(forms.Form):
    nueva_password = forms.CharField(
        max_length=128,
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Nueva contraseña'
    )

    def clean_nueva_password(self):
        password = self.cleaned_data['nueva_password']
        from django.contrib.auth.password_validation import validate_password
        validate_password(password)
        return password


class EditarCuentaEntrenadorForm(forms.Form):
    first_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}), label='Nombre(s)')
    last_name = forms.CharField(max_length=30, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}), label='Apellido(s)')
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control'}), label='Correo electrónico')


class SolicitudCambioContrasenaForm(forms.ModelForm):
    class Meta:
        model = SolicitudCambioContrasena
        fields = []