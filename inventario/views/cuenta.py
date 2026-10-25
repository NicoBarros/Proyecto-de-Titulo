from django.contrib import messages
from django.contrib.auth.views import PasswordChangeView
from django.urls import reverse_lazy

from ..seguridad import registrar_cambio_cuenta


class CambiarContrasenaView(PasswordChangeView):
    template_name = 'inventario/cambiar_contrasena.html'
    success_url = reverse_lazy('dashboard')

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        registrar_cambio_cuenta(self.request, self.request.user, 'contraseña cambiada por el titular')
        messages.success(self.request, 'Tu contraseña se actualizó correctamente.')
        return respuesta
