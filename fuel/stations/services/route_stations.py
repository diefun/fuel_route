"""Find fuel stations along a route and their position (mile marker) on it.

Approach:
- All geocoded stations are loaded ONCE per process into a KD-tree (fast spatial index).
- The route polyline is densified to ~1-mile steps, so "distance to the nearest route
  point" is a good approximation of "distance to the route".
- Each station near the route gets the cumulative distance of its nearest route point
  as its mile marker.

Coordinates are converted to 3D cartesian (x, y, z) in miles, because a KD-tree uses
straight-line (euclidean) distance. At the scales we care about (a few miles), the
straight-line distance through the Earth is practically equal to the surface distance.
"""
import threading
import numpy as np

from dataclasses import dataclass
from scipy.spatial import cKDTree
from stations.models import FuelStation


EARTH_RADIUS_MILES = 3958.8


def haversine_miles(lat1, lon1, lat2, lon2):
    """Great-circle distance in miles. Works with scalars or numpy arrays."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(a))


def to_xyz(lat, lon):
    """Lat/lon in degrees -> array of shape (N, 3) with 3D coordinates in miles."""
    lat = np.radians(np.asarray(lat, dtype=float))
    lon = np.radians(np.asarray(lon, dtype=float))
    return np.column_stack((
        EARTH_RADIUS_MILES * np.cos(lat) * np.cos(lon),
        EARTH_RADIUS_MILES * np.cos(lat) * np.sin(lon),
        EARTH_RADIUS_MILES * np.sin(lat),
    ))


def densify(points, step_miles=1.0):
    """Adds interpolated points so no segment is longer than `step_miles`.

    OSRM can leave several miles between points on straight highways; without this,
    a station right next to the road could look far from the nearest route point.
    """
    if len(points) < 2:
        return points
    seg = haversine_miles(points[:-1, 0], points[:-1, 1], points[1:, 0], points[1:, 1])
    n = np.maximum(1, np.ceil(seg / step_miles).astype(int))   # sub-segments per segment
    seg_idx = np.repeat(np.arange(len(seg)), n)                  # which segment each new point belongs to
    step = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)   # 0, 1, ..., n-1 within each segment
    t = (step / np.repeat(n, n))[:, None]                        # fraction along the segment
    dense = points[seg_idx] + t * (points[seg_idx + 1] - points[seg_idx])
    return np.vstack((dense, points[-1:]))


@dataclass(frozen=True)
class RouteStation:
    station: FuelStation
    mile: float          # position along the route, in miles from the origin
    offset_miles: float  # straight-line distance from the route


class StationIndex:
    def __init__(self, stations):
        stations = [s for s in stations if s.latitude is not None and s.longitude is not None]
        if not stations:
            raise RuntimeError("No geocoded stations. Run `manage.py import_fuel_prices` first.")
        self.stations = stations
        self.tree = cKDTree(to_xyz([s.latitude for s in stations], [s.longitude for s in stations]))

    def along_route(self, coords, max_offset_miles=10.0, total_miles=None):
        """Stations within `max_offset_miles` of the route, sorted by mile marker.

        coords: list of (lat, lon) from the router.
        total_miles: the router's driving distance. If given, mile markers are rescaled
        to it, so they are consistent with the distance reported by the API.
        """
        route = densify(np.asarray(coords, dtype=float))
        seg = haversine_miles(route[:-1, 0], route[:-1, 1], route[1:, 0], route[1:, 1])
        cumulative = np.concatenate(([0.0], np.cumsum(seg)))
        if total_miles and cumulative[-1] > 0:
            cumulative *= total_miles / cumulative[-1]

        route_tree = cKDTree(to_xyz(route[:, 0], route[:, 1]))

        # 1) candidates: stations within the radius of ANY route point (tree vs tree)
        hits = route_tree.query_ball_tree(self.tree, r=max_offset_miles)
        candidate_ids = sorted({i for group in hits for i in group})
        if not candidate_ids:
            return []

        # 2) for each candidate, its nearest route point -> offset and mile marker
        cand = [self.stations[i] for i in candidate_ids]
        dist, nearest = route_tree.query(to_xyz([s.latitude for s in cand], [s.longitude for s in cand]))

        result = [
            RouteStation(station=s, mile=float(cumulative[p]), offset_miles=float(d))
            for s, d, p in zip(cand, dist, nearest)
        ]
        result.sort(key=lambda rs: rs.mile)
        return result

    def nearest(self, lat, lon):
        """Closest geocoded station to a point -> (station, distance in miles)."""
        _, idx = self.tree.query(to_xyz([lat], [lon])[0])
        s = self.stations[int(idx)]
        return s, float(haversine_miles(lat, lon, s.latitude, s.longitude))


# --- Process-level cache: build the index once, reuse it on every request ----------
_index = None
_lock = threading.Lock()


def get_station_index():
    global _index
    if _index is None:
        with _lock:
            if _index is None:
                _index = StationIndex(list(FuelStation.objects.filter(latitude__isnull=False)))
    return _index


def reset_station_index():
    """Call after re-importing prices so the next request rebuilds the index."""
    global _index
    _index = None