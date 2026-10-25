import hmac

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .. import tareas


@csrf_exempt
@require_POST
def tareas_view(request):
    recibido = request.headers.get('Authorization', '').removeprefix('Bearer ')
    if not settings.TAREAS_TOKEN or not hmac.compare_digest(recibido, settings.TAREAS_TOKEN):
        return JsonResponse({'error': 'No autorizado'}, status=401)
    return JsonResponse(tareas.ejecutar())
