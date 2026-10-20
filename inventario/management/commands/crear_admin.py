import os

from django.core.management.base import BaseCommand

from inventario.models import Usuario


class Command(BaseCommand):
    help = 'Crea el superusuario administrador a partir de ADMIN_EMAIL y ADMIN_PASSWORD.'

    def handle(self, *args, **kwargs):
        email = os.environ.get('ADMIN_EMAIL', '').strip().lower()
        password = os.environ.get('ADMIN_PASSWORD', '')
        if not email or not password:
            self.stdout.write('ADMIN_EMAIL o ADMIN_PASSWORD no están definidos; no se crea el administrador.')
            return

        usuario = Usuario.objects.filter(email=email).first()
        if usuario:
            if not usuario.is_superuser:
                usuario.is_staff = usuario.is_superuser = usuario.is_active = True
                usuario.rol = Usuario.Rol.ENCARGADO_LABORATORIO
                usuario.save(update_fields=['is_staff', 'is_superuser', 'is_active', 'rol'])
                self.stdout.write(self.style.SUCCESS(f'{email} ahora es administrador.'))
            else:
                self.stdout.write(f'El administrador {email} ya existe.')
            return

        username = base = email.split('@')[0]
        n = 1
        while Usuario.objects.filter(username=username).exists():
            username = f'{base}_{n}'
            n += 1
        Usuario.objects.create_superuser(
            username=username, email=email, password=password,
            rol=Usuario.Rol.ENCARGADO_LABORATORIO,
        )
        self.stdout.write(self.style.SUCCESS(f'Administrador {email} creado.'))
