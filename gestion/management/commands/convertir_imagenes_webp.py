import os
from io import BytesIO

from PIL import Image
from django.core.files import File
from django.core.management.base import BaseCommand

from gestion.models import Equipo, Jugador, MiembroStaff, PerfilEntrenador

MODELOS_CAMPOS = [
    (Jugador, ['foto_perfil']),
    (Equipo, ['logo']),
    (MiembroStaff, ['foto']),
    (PerfilEntrenador, ['foto']),
]


class Command(BaseCommand):
    help = 'Convierte todas las imagenes PNG/JPG existentes a WebP'

    def handle(self, *args, **options):
        total = 0

        for modelo, campos in MODELOS_CAMPOS:
            qs = list(modelo.objects.all())
            for obj in qs:
                actualizar = []
                for campo in campos:
                    archivo = getattr(obj, campo, None)
                    if not archivo or not archivo.name:
                        continue
                    if os.path.splitext(archivo.name)[1].lower() in ('.webp', '.pdf'):
                        continue
                    try:
                        img = Image.open(archivo)
                        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                            img = img.convert('RGBA')
                        else:
                            img = img.convert('RGB')
                        buf = BytesIO()
                        img.save(buf, format='WEBP', quality=80, optimize=True)
                        webp = os.path.splitext(archivo.name)[0] + '.webp'
                        archivo.save(webp, File(buf), save=False)
                        actualizar.append(campo)
                        total += 1
                        self.stdout.write(f"  {obj._meta.model.__name__}.{campo}: {webp}")
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f"  Error {obj._meta.model.__name__}.{campo} (id={obj.pk}): {e}"))

                if actualizar:
                    obj.save(update_fields=actualizar)

            self.stdout.write(f" {modelo.__name__}: procesados {len(qs)} registros")

        self.stdout.write(self.style.SUCCESS(f"Total imagenes convertidas: {total}"))
