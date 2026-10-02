import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from stations.services.geo import LocationError
from stations.services.optimizer import InfeasibleRouteError
from stations.services.planner import plan_trip
from stations.services.routing import RoutingError
from urllib.parse import urlencode


def _plan_or_error(start, finish):
    """Shared by both views: returns (plan, None) or (None, error JsonResponse)."""
    if not start or not finish:
        return None, JsonResponse({"error": "Both 'start' and 'finish' are required."}, status=400)
    try:
        return plan_trip(start, finish), None
    except LocationError as e:
        return None, JsonResponse({"error": str(e)}, status=400)
    except InfeasibleRouteError as e:
        return None, JsonResponse({"error": str(e)}, status=422)
    except RoutingError as e:
        return None, JsonResponse({"error": str(e)}, status=502)


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
    plan, error = _plan_or_error(start, finish)
    if error:
        return error

    map_url = request.build_absolute_uri("/api/route/map/?" + urlencode({"start": start, "finish": finish}))
    return JsonResponse({**plan, "map_url": map_url})


@require_http_methods(["GET"])
def route_map(request):
    """HTML page with the route drawn on a map. Uses the same cached plan -> no extra routing call."""
    plan, error = _plan_or_error(request.GET.get("start"), request.GET.get("finish"))
    if error:
        return error
    return render(request, "stations/map.html", {"plan": plan})