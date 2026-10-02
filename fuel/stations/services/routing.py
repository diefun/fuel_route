import requests
from dataclasses import dataclass
from config.settings import ROUTING

@dataclass
class Route:
    coords: list[tuple[float, float]]
    distance_miles: float
    duration_hours: float


class RoutingError(Exception):
    pass


def _validate(point, label):
    lat, lon = point
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise RoutingError(f"Invalid {label} coordinates: {point}")
    

def get_route(origin, dest) -> Route:
    _validate(origin, "origin")
    _validate(dest, "destination")
    
    url = f"{ROUTING['OSRM_URL']}/route/v1/driving/{origin[1]},{origin[0]};{dest[1]},{dest[0]}"
    params = {
        "overview": "full",
        "geometries": "geojson",
    }

    try:
        response = requests.get(url, params=params, timeout=ROUTING["TIMEOUT_SECONDS"])
        response.raise_for_status()
        data = response.json()
        
        if data["code"] != "Ok":
            raise RoutingError(f"Routing error: {data['code']}")
        
        route_data = data["routes"][0]
        distance_miles = route_data["distance"] * 0.000621371  # meters to miles
        duration_hours = route_data["duration"] / 3600  # seconds to hours
        geometry = data["routes"][0]["geometry"]["coordinates"]   # [[lon, lat], ...]
        coords = [(lat, lon) for lon, lat in geometry]
        
        return Route(coords=coords, distance_miles=distance_miles, duration_hours=duration_hours)
    
    except requests.RequestException as e:
        raise RoutingError(f"Request error: {e}") from e