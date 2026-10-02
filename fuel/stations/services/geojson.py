"""Builds the GeoJSON map returned by the API.

GeoJSON is the standard format for map data: any map library (Leaflet, Mapbox,
Google Maps) or tool (geojson.io) can draw it directly.

IMPORTANT: GeoJSON uses [longitude, latitude] order, the opposite of the
(lat, lon) tuples used in the rest of the project.
"""

MAX_ROUTE_POINTS = 1500  # enough detail to draw the route, keeps the response small


def simplify(coords, max_points=MAX_ROUTE_POINTS):
    """Keep every n-th point so the line has at most ~max_points (always keeps the last one).

    A coast-to-coast route from OSRM can have tens of thousands of points, which would make
    the JSON response several MB. At map zoom levels, 1500 points look the same.
    """
    step = max(1, len(coords) // max_points)
    simplified = list(coords[::step])

    if simplified[-1] != coords[-1]:
        simplified.append(coords[-1])
    
    return simplified


def _point(lat, lon, properties):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": properties,
    }


def build_route_geojson(route_coords, origin, dest, fuel_stops):
    """FeatureCollection with the route (LineString), start, finish and fuel stops (Points).

    route_coords: list of (lat, lon) from the router
    origin, dest: (lat, lon)
    fuel_stops: the list of stop dicts already built for the API response
    """
    line = [[lon, lat] for lat, lon in simplify(route_coords)]

    features = [
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": line},
            "properties": {"kind": "route"},
        },
        _point(origin[0], origin[1], {"kind": "start"}),
        _point(dest[0], dest[1], {"kind": "finish"}),
    ]
    
    for number, stop in enumerate(fuel_stops, start=1):
        features.append(_point(stop["latitude"], stop["longitude"], {
            "kind": "fuel_stop",
            "stop_number": number,
            "name": stop["name"],
            "city": stop["city"],
            "state": stop["state"],
            "price_per_gallon": stop["price_per_gallon"],
            "gallons": stop["gallons"],
            "cost": stop["cost"],
        }))

    return {"type": "FeatureCollection", "features": features}