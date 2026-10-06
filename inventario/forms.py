from django import forms
from .models import Equipo, Insumo, Solicitud

class EquipoForm(forms.ModelForm):
    class Meta:
        model = Equipo
        fields = ['codigo_inventario', 'nombre', 'modelo', 'especificaciones', 'ubicacion', 'valor_adquisicion']


class InsumoForm(forms.ModelForm):
    class Meta:
        model = Insumo
        fields = ['nombre', 'categoria', 'tipo', 'cantidad_total', 'umbral_minimo']


class MantenimientoForm(forms.Form):
    equipo_id = forms.IntegerField()
    falla_descrita = forms.CharField(required=True)
    costo_cotizado = forms.DecimalField(required=True, max_digits=12, decimal_places=2)
