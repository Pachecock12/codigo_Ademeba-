from django.core.management.base import BaseCommand
from django.conf import settings
from django.urls import reverse
from io import BytesIO
from django.core.files import File
import qrcode

from gestion.models import Jugador


class Command(BaseCommand):
    help = 'Regenera los códigos QR de todos los jugadores con la URL dinámica actual'

    def handle(self, *args, **options):
        jugadores = Jugador.objects.all()
        total = jugadores.count()
        if total == 0:
            self.stdout.write(self.style.WARNING('No hay jugadores registrados'))
            return

        for i, jugador in enumerate(jugadores, 1):
            ruta_valida = reverse('validar_jugador_qr', args=[jugador.id])
            qr_content = f"{settings.SITE_URL}{ruta_valida}"

            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(qr_content)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffer = BytesIO()
            img.save(buffer, format='PNG')

            jugador.codigo_qr.save(f'qr_{jugador.curp}.png', File(buffer), save=False)
            jugador.save(update_fields=['codigo_qr'])

            self.stdout.write(f"[{i}/{total}] QR regenerado: {jugador.nombres} {jugador.apellido_paterno}")

        self.stdout.write(self.style.SUCCESS(f'QR regenerados para {total} jugadores'))
