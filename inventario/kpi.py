from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.utils import timezone

from .models import Equipo, Insumo, Mantenimiento, Movimiento, Solicitud

PERIODOS = [7, 30, 90, 365]

METAS = {
    'aprobacion_horas': 24,
    'devoluciones_a_tiempo': 90,
    'disponibilidad': 70,
    'uso_equipos': 50,
    'atrasos_activos': 0,
    'stock_critico': 10,
    'reparacion_dias': 7,
}


@dataclass
class Indicador:
    clave: str
    nombre: str
    icono: str
    valor: float | None
    unidad: str
    meta: float
    menor_es_mejor: bool
    detalle: str
    texto_valor: str | None = None

    @property
    def cumple(self):
        if self.valor is None:
            return None
        return self.valor <= self.meta if self.menor_es_mejor else self.valor >= self.meta

    @property
    def texto(self):
        if self.valor is None:
            return 'Sin datos'
        return self.texto_valor or f'{_numero(self.valor)}{self.unidad}'

    @property
    def objetivo(self):
        return f"{'≤' if self.menor_es_mejor else '≥'} {_numero(self.meta)}{self.unidad}"


def _numero(valor):
    texto = f'{valor:.1f}'.replace('.', ',')
    return texto[:-2] if texto.endswith(',0') else texto


def _cantidad(n, singular, plural):
    return f'{n} {singular if n == 1 else plural}'


def _porcentaje(parte, total):
    return parte * 100 / total if total else None


def _duracion(fin, inicio):
    return ExpressionWrapper(F(fin) - F(inicio), output_field=DurationField())


def _texto_horas(horas):
    if horas is None or horas >= 1:
        return None
    minutos = horas * 60
    return '< 1 min' if minutos < 1 else f'{round(minutos)} min'


def calcular_kpis(dias=30):
    desde = timezone.now() - timedelta(days=dias)
    Solicitud.marcar_atrasadas()

    aprobacion = Solicitud.objects.filter(fecha_aprobacion__gte=desde).aggregate(
        promedio=Avg(_duracion('fecha_aprobacion', 'created_at')), total=Count('id'),
    )
    horas_aprobacion = aprobacion['promedio'].total_seconds() / 3600 if aprobacion['promedio'] is not None else None

    devoluciones = Movimiento.objects.filter(tipo=Movimiento.TipoMovimiento.DEVOLUCION, fecha__gte=desde).aggregate(
        total=Count('id'),
        a_tiempo=Count('id', filter=Q(solicitud__estado=Solicitud.EstadoSolicitud.DEVUELTA)),
    )

    operativos = Equipo.objects.exclude(estado=Equipo.Estado.FUERA_SERVICIO)
    inventario = operativos.aggregate(
        total=Count('id'), disponibles=Count('id', filter=Q(estado=Equipo.Estado.DISPONIBLE)),
    )
    usados = operativos.filter(
        solicituditem__solicitud__movimientos__tipo=Movimiento.TipoMovimiento.ENTREGA,
        solicituditem__solicitud__movimientos__fecha__gte=desde,
    ).aggregate(total=Count('id', distinct=True))['total']

    atrasadas = Solicitud.objects.filter(estado=Solicitud.EstadoSolicitud.ATRASADA).count()

    insumos = Insumo.objects.aggregate(
        total=Count('id'), criticos=Count('id', filter=Q(cantidad_disponible__lte=F('umbral_minimo'))),
    )

    reparacion = Mantenimiento.objects.filter(
        decision=Mantenimiento.Decision.COMPLETADO, fecha_resolucion__gte=desde,
    ).aggregate(promedio=Avg(_duracion('fecha_resolucion', 'fecha_diagnostico')), total=Count('id'))
    dias_reparacion = reparacion['promedio'].total_seconds() / 86400 if reparacion['promedio'] is not None else None

    return [
        Indicador(
            'aprobacion_horas', 'Tiempo promedio de aprobación', 'bi-hourglass-split',
            horas_aprobacion, ' h', METAS['aprobacion_horas'], True,
            _cantidad(aprobacion['total'], 'solicitud aprobada', 'solicitudes aprobadas'),
            _texto_horas(horas_aprobacion),
        ),
        Indicador(
            'devoluciones_a_tiempo', 'Devoluciones a tiempo', 'bi-calendar-check',
            _porcentaje(devoluciones['a_tiempo'], devoluciones['total']), ' %', METAS['devoluciones_a_tiempo'], False,
            f"{devoluciones['a_tiempo']} de {_cantidad(devoluciones['total'], 'devolución', 'devoluciones')}",
        ),
        Indicador(
            'disponibilidad', 'Disponibilidad del inventario', 'bi-box-seam',
            _porcentaje(inventario['disponibles'], inventario['total']), ' %', METAS['disponibilidad'], False,
            f"{inventario['disponibles']} de {_cantidad(inventario['total'], 'equipo operativo', 'equipos operativos')}",
        ),
        Indicador(
            'uso_equipos', 'Tasa de uso de equipos', 'bi-graph-up-arrow',
            _porcentaje(usados, inventario['total']), ' %', METAS['uso_equipos'], False,
            f"{usados} de {_cantidad(inventario['total'], 'equipo', 'equipos')} prestados",
        ),
        Indicador(
            'atrasos_activos', 'Préstamos atrasados activos', 'bi-exclamation-octagon',
            atrasadas, '', METAS['atrasos_activos'], True, 'Estado actual',
        ),
        Indicador(
            'stock_critico', 'Insumos con stock crítico', 'bi-droplet-half',
            _porcentaje(insumos['criticos'], insumos['total']), ' %', METAS['stock_critico'], True,
            f"{insumos['criticos']} de {_cantidad(insumos['total'], 'insumo', 'insumos')}",
        ),
        Indicador(
            'reparacion_dias', 'Tiempo promedio de reparación', 'bi-tools',
            dias_reparacion, ' días', METAS['reparacion_dias'], True,
            _cantidad(reparacion['total'], 'reparación completada', 'reparaciones completadas'),
        ),
    ]
