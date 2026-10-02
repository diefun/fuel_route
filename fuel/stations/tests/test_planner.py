"""Tests for plan_trip: the whole flow with the external pieces mocked.

- parse_location is mocked -> no gazetteer files needed
- get_route is mocked      -> no network calls
- stations are created in the test database (that's why this is a TestCase)
"""
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from stations.models import FuelStation
from stations.services.route_stations import reset_station_index
from stations.services.routing import Route
from stations.services.planner import plan_trip

# Fake trip: straight line going north along longitude -97, from lat 30 to lat 38 (~550 miles)
ORIGIN, DEST = (30.0, -97.0), (38.0, -97.0)
LOCATIONS = {"Start, TX": ORIGIN, "End, KS": DEST}
FAKE_ROUTE = Route(
    coords=[(30.0 + i * 0.08, -97.0) for i in range(101)],
    distance_miles=550.0,
    duration_hours=8.5,
)


class PlanTripTests(TestCase):
    def setUp(self):
        cache.clear()            # no plans left over from other tests
        reset_station_index()    # rebuild the index with THIS test's stations
        for opis_id, lat, price in [
            (1, 30.0, "3.50"),   # at the origin -> first stop (tank starts empty)
            (2, 32.0, "3.00"),   # ~mile 138, cheaper
            (3, 35.0, "3.80"),   # ~mile 345
            (4, 37.0, "3.20"),   # ~mile 483
        ]:
            FuelStation.objects.create(opis_id=opis_id, name=f"Station {opis_id}", city="X", state="TX",
                                       price=Decimal(price), latitude=lat, longitude=-97.0)

    def tearDown(self):
        reset_station_index()    # don't leak this test's stations into other tests

    def run_plan(self, mock_route):
        mock_route.return_value = FAKE_ROUTE
        with mock.patch("stations.services.planner.parse_location", side_effect=LOCATIONS.get):
            return plan_trip("Start, TX", "End, KS")

    @mock.patch("stations.services.planner.get_route")
    def test_plan_basic_fields(self, mock_route):
        result = self.run_plan(mock_route)
        self.assertEqual(result["distance_miles"], 550.0)
        self.assertAlmostEqual(result["total_gallons"], 55.0, places=1)  # 550 mi / 10 mpg
        self.assertGreater(result["total_fuel_cost"], 0)
        self.assertEqual(result["fuel_stops"][0]["mile_marker"], 0.0)  # first stop at the origin

    @mock.patch("stations.services.planner.get_route")
    def test_total_cost_matches_sum_of_stops(self, mock_route):
        result = self.run_plan(mock_route)
        self.assertAlmostEqual(result["total_fuel_cost"], sum(s["cost"] for s in result["fuel_stops"]), places=1)

    @mock.patch("stations.services.planner.get_route")
    def test_second_call_uses_cache(self, mock_route):
        first = self.run_plan(mock_route)
        second = self.run_plan(mock_route)
        self.assertFalse(first["meta"]["cached"])
        self.assertEqual(first["meta"]["routing_api_calls"], 1)
        self.assertTrue(second["meta"]["cached"])
        self.assertEqual(second["meta"]["routing_api_calls"], 0)
        mock_route.assert_called_once()   # OSRM "called" only once for two requests