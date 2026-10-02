import time

from django.core.cache import cache
from stations.services.geo import parse_location
from stations.services.geojson import build_route_geojson
from stations.services.optimizer import Stop, plan_fuel_stops
from stations.services.route_stations import get_station_index
from stations.services.routing import get_route

MAX_RANGE_MILES = 500
MPG = 10
MAX_OFFSET_MILES = 10


def _compute_plan(start, finish, origin, dest) -> dict:
    """Route from start to finish with the cheapest fuel stops and total fuel cost."""
    t0 = time.perf_counter()
    route = get_route(origin, dest)
    index = get_station_index()
    first_station, _ = index.nearest(*origin)
    along = index.along_route(route.coords, MAX_OFFSET_MILES, route.distance_miles)

    stops = [Stop(0.0, float(first_station.price), first_station)]
    stops += [
        Stop(rs.mile, float(rs.station.price), rs.station)
        for rs in along
        if rs.station.pk != first_station.pk
    ]

    plan = plan_fuel_stops(stops, route.distance_miles, MAX_RANGE_MILES, MPG)
    fuel_stops = [
        {
            "name": p.stop.ref.name,
            "city": p.stop.ref.city,
            "state": p.stop.ref.state,
            "latitude": p.stop.ref.latitude,
            "longitude": p.stop.ref.longitude,
            "mile_marker": round(p.stop.mile, 1),
            "price_per_gallon": float(p.stop.ref.price),
            "gallons": round(p.gallons, 2),
            "cost": round(p.cost, 2),
        }
        for p in plan.purchases
    ]

    return {
        "start": {"query": start, "latitude": origin[0], "longitude": origin[1]},
        "finish": {"query": finish, "latitude": dest[0], "longitude": dest[1]},
        "distance_miles": round(route.distance_miles, 1),
        "total_gallons": round(plan.total_gallons, 2),
        "total_fuel_cost": round(plan.total_cost, 2),
        "fuel_stops": fuel_stops,
        "map": build_route_geojson(route.coords, origin, dest, fuel_stops),
    }


def plan_trip(start: str, finish: str) -> dict:
    t0 = time.perf_counter()
    origin = parse_location(start)
    dest = parse_location(finish)
    key = f"plan:{origin[0]:.4f},{origin[1]:.4f}:{dest[0]:.4f},{dest[1]:.4f}"
    result = cache.get(key)

    if result is None:
        result = _compute_plan(start, finish, origin, dest)
        cache.set(key, result)
        cached = False
    else:
        cached = True

    result["meta"] = {
        "routing_api_calls": 0 if cached else 1,
        "cached": cached,
        "elapsed_ms": round((time.perf_counter() - t0) * 1000, 1),
    }
    return result