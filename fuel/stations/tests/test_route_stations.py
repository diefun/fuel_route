from decimal import Decimal

import numpy as np
from django.test import SimpleTestCase

from stations.models import FuelStation
from stations.services.route_stations import StationIndex, densify, haversine_miles

# Straight route going north along longitude -97, from lat 30 to lat 32 (~138 miles)
ROUTE = [(30.0 + i * 0.04, -97.0) for i in range(51)]
MILES_PER_DEG_LON_AT_31 = 69.17 * np.cos(np.radians(31))


def station(opis_id, lat, lon, price="3.50"):
    # Unsaved model instances: no database needed
    return FuelStation(opis_id=opis_id, name=f"S{opis_id}", city="X", state="TX",
                       price=Decimal(price), latitude=lat, longitude=lon)


class HaversineTests(SimpleTestCase):
    def test_one_degree_of_latitude(self):
        self.assertAlmostEqual(haversine_miles(30, -97, 31, -97), 69.09, delta=0.1)

    def test_vectorized(self):
        d = haversine_miles(np.array([30, 30]), np.array([-97, -97]), np.array([31, 32]), np.array([-97, -97]))
        self.assertEqual(d.shape, (2,))


class DensifyTests(SimpleTestCase):
    def test_no_segment_longer_than_step(self):
        pts = np.array([(30.0, -97.0), (31.0, -97.0)])  # ~69 miles
        dense = densify(pts, step_miles=1.0)
        seg = haversine_miles(dense[:-1, 0], dense[:-1, 1], dense[1:, 0], dense[1:, 1])
        self.assertLessEqual(seg.max(), 1.0 + 1e-9)
        np.testing.assert_allclose(dense[0], pts[0])
        np.testing.assert_allclose(dense[-1], pts[-1])


class AlongRouteTests(SimpleTestCase):
    def setUp(self):
        self.index = StationIndex([
            station(1, 31.0, -97.0),                                   # on the route, ~mile 69
            station(2, 30.5, -97.0 + 5 / MILES_PER_DEG_LON_AT_31),     # ~5 mi east, ~mile 35
            station(3, 31.5, -97.0 + 50 / MILES_PER_DEG_LON_AT_31),    # ~50 mi east -> excluded
            station(4, None, None),                                    # not geocoded -> ignored
        ])

    def test_returns_only_nearby_stations_sorted_by_mile(self):
        result = self.index.along_route(ROUTE, max_offset_miles=10)
        self.assertEqual([rs.station.opis_id for rs in result], [2, 1])

    def test_mile_markers_and_offsets(self):
        result = {rs.station.opis_id: rs for rs in self.index.along_route(ROUTE, max_offset_miles=10)}
        self.assertAlmostEqual(result[1].mile, 69.1, delta=1.5)
        self.assertAlmostEqual(result[1].offset_miles, 0, delta=0.5)
        self.assertAlmostEqual(result[2].mile, 34.5, delta=1.5)
        self.assertAlmostEqual(result[2].offset_miles, 5, delta=0.5)

    def test_rescales_to_router_distance(self):
        result = {rs.station.opis_id: rs for rs in self.index.along_route(ROUTE, 10, total_miles=276.4)}
        self.assertAlmostEqual(result[1].mile, 138.2, delta=3)  # same position, doubled scale

    def test_no_stations_near_route(self):
        far_route = [(45.0, -70.0), (45.5, -70.0)]
        self.assertEqual(self.index.along_route(far_route, 10), [])