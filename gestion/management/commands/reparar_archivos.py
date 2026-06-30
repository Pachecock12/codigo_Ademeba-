import os
from django.core.management.base import BaseCommand
from django.core.files import File
from gestion.models import Equipo, Jugador, MiembroStaff, PerfilEntrenador, Adeudo


class Command(BaseCommand):
    help = 'Re-sube archivos locales faltantes y regenera QR de jugadores'

    def handle(self, *args, **options):
        recontados = 0

        for j in Jugador.objects.all():
            if j.codigo_qr and not j.codigo_qr.storage.exists(j.codigo_qr.name):
                j.save()
                self.stdout.write(f'  QR regenerado: {j.nombres} {j.apellido_paterno}')
                recontados += 1

        self.stdout.write(self.style.SUCCESS(f'QR regenerados: {recontados}'))
