from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def url_pagina(context, parametro, numero):
    consulta = context['request'].GET.copy()
    consulta[parametro] = numero
    return f'?{consulta.urlencode()}'
