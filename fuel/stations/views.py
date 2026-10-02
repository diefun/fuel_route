import json

from django.http import JsonResponse
from stations.services.geo import LocationError
from stations.services.optimizer import InfeasibleRouteError
from stations.services.planner import plan_trip
from stations.services.routing import RoutingError
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


@csrf_exempt
@require_http_methods(["GET", "POST"])
def route_plan(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON body."}, status=400)
    else:
        data = request.GET

    start, finish = data.get("start"), data.get("finish")
    
    if not start or not finish:
        return JsonResponse({"error": "Both 'start' and 'finish' are required."}, status=400)

    try:
        return JsonResponse(plan_trip(start, finish))
    except LocationError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except InfeasibleRouteError as e:
        return JsonResponse({"error": str(e)}, status=422)
    except RoutingError as e:
        return JsonResponse({"error": str(e)}, status=502)