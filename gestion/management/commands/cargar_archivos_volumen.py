import os
from django.core.management.base import BaseCommand, CommandError
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
    help = 'Copia archivos desde un directorio local al storage activo (Railway Volume)'

    def add_arguments(self, parser):
        parser.add_argument('origen', nargs='?', default=None,
                            help='Directorio raiz con los archivos (ej: /ruta/a/media/)')

    def handle(self, *args, **options):
        origen = options.get('origen')
        if not origen:
            origen = os.path.join(settings.BASE_DIR, 'media')
            self.stdout.write(f'Sin argumento, usando MEDIA_ROOT local: {origen}')

        if not os.path.isdir(origen):
            raise CommandError(f'El directorio {origen} no existe o no es accesible')

        total = 0
        for modelo, campos in MODELOS:
            for instancia in modelo.objects.all():
                for campo in campos:
                    field = getattr(instancia, campo)
                    if not field:
                        continue
                    nombre = field.name
                    ruta = os.path.join(origen, nombre)
                    if os.path.exists(ruta):
                        with open(ruta, 'rb') as f:
                            field.save(nombre, File(f), save=False)
                        total += 1
                        self.stdout.write(f'  [{modelo.__name__}] {nombre}')
                    else:
                        self.stdout.write(self.style.WARNING(f'  NO ENCONTRADO: {ruta}'))
                if any(getattr(instancia, c) for c in campos):
                    instancia.save(update_fields=[c for c in campos if getattr(instancia, c)])
        self.stdout.write(self.style.SUCCESS(f'Archivos copiados: {total}'))
