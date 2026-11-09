from django import forms
from django.utils import timezone

from .models import Equipo, Insumo


class EquipoForm(forms.ModelForm):
    class Meta:
        model = Equipo
        fields = ['codigo_inventario', 'nombre', 'modelo', 'especificaciones', 'ubicacion', 'valor_adquisicion', 'fecha_adquisicion']

    def clean_fecha_adquisicion(self):
        fecha = self.cleaned_data.get('fecha_adquisicion')
        if fecha and fecha > timezone.localdate():
            raise forms.ValidationError('La fecha de adquisición no puede ser futura.')
        return fecha


class InsumoForm(forms.ModelForm):
    class Meta:
        model = Insumo
        fields = ['nombre', 'categoria', 'tipo', 'cantidad_total', 'umbral_minimo']


class MantenimientoForm(forms.Form):
    equipo_id = forms.IntegerField()
    falla_descrita = forms.CharField(required=True)
    costo_cotizado = forms.DecimalField(required=True, max_digits=12, decimal_places=2, min_value=0)
