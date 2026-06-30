import os
from django.core.management.base import BaseCommand
from django.core.files import File
from django.conf import settings
from gestion.models import Equipo, Jugador, MiembroStaff, PerfilEntrenador, Adeudo

MODELOS = [
    (Equipo, ['logo']),
    (Jugador, ['foto_perfil', 'archivo_curp', 'archivo_identificacion',
               'acta_nacimiento', 'credencial_escolar', 'archivo_afiliacion',
               'archivo_pago', 'codigo_qr']),
    (MiembroStaff, ['foto']),
    (PerfilEntrenador, ['foto']),
    (Adeudo, ['voucher_comprobante']),
]


class Command(BaseCommand):
    help = 'Sube archivos locales a Supabase Storage (S3)'

    def handle(self, *args, **options):
        total = 0
        for modelo, campos in MODELOS:
            for instancia in modelo.objects.all():
                for campo in campos:
                    field = getattr(instancia, campo)
                    if field and os.path.exists(field.path):
                        nombre = field.name
                        with open(field.path, 'rb') as f:
                            field.save(nombre, File(f), save=False)
                        total += 1
                        self.stdout.write(f'  [{modelo.__name__}] {nombre}')
                if any(getattr(instancia, c) for c in campos):
                    instancia.save(update_fields=[c for c in campos if getattr(instancia, c)])
        self.stdout.write(self.style.SUCCESS(f'Archivos subidos: {total}'))
