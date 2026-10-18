from .models import Equipo, HistorialEquipo

CAMPOS_AUDITADOS = {
    'codigo_inventario': 'Código',
    'nombre': 'Nombre',
    'modelo': 'Modelo',
    'especificaciones': 'Especificaciones',
    'ubicacion': 'Ubicación',
    'estado': 'Estado',
    'valor_adquisicion': 'Valor de adquisición',
}


def foto(equipo):
    datos = {}
    for campo in CAMPOS_AUDITADOS:
        valor = getattr(equipo, campo)
        datos[campo] = None if valor in (None, '') else str(valor)
    return datos


def registrar(equipo, usuario, accion, antes=None, detalle=''):
    actual = foto(equipo)
    if accion == HistorialEquipo.Accion.ELIMINADO:
        cambios = {c: [v, None] for c, v in actual.items() if v is not None}
    elif antes is None:
        cambios = {c: [None, v] for c, v in actual.items() if v is not None}
    else:
        cambios = {c: [antes[c], actual[c]] for c in CAMPOS_AUDITADOS if antes[c] != actual[c]}
        if not cambios:
            return None
    return HistorialEquipo.objects.create(
        equipo=equipo if equipo.pk else None,
        codigo_inventario=equipo.codigo_inventario,
        usuario=usuario if usuario and usuario.is_authenticated else None,
        accion=accion,
        cambios=cambios,
        detalle=detalle[:255],
    )


def etiqueta_valor(campo, valor):
    if valor is None:
        return '—'
    if campo == 'estado':
        return dict(Equipo.Estado.choices).get(valor, valor)
    return valor
