"""Tests for the GeoJSON builder and the HTML map view."""
from unittest import mock

from django.test import SimpleTestCase

from stations.services.geojson import build_route_geojson, simplify

ORIGIN, DEST = (30.0, -97.0), (38.0, -97.0)
STOPS = [
    {"name": "Station 1", "city": "Austin", "state": "TX", "latitude": 30.0, "longitude": -97.0,
     "mile_marker": 0.0, "price_per_gallon": 3.5, "gallons": 13.8, "cost": 48.3},
    {"name": "Station 2", "city": "Waco", "state": "TX", "latitude": 32.0, "longitude": -97.0,
     "mile_marker": 138.0, "price_per_gallon": 3.0, "gallons": 41.2, "cost": 123.6},
]
ROUTE = [(30.0 + i * 0.08, -97.0) for i in range(101)]


class GeoJsonTests(SimpleTestCase):
    def setUp(self):
        self.geo = build_route_geojson(ROUTE, ORIGIN, DEST, STOPS)

    def test_is_a_feature_collection(self):
        self.assertEqual(self.geo["type"], "FeatureCollection")
        kinds = [f["properties"]["kind"] for f in self.geo["features"]]
        self.assertEqual(kinds, ["route", "start", "finish", "fuel_stop", "fuel_stop"])

    def test_uses_lon_lat_order(self):
        # GeoJSON is [lon, lat]: the first number must be the longitude (-97), not the latitude (30)
        line = self.geo["features"][0]["geometry"]["coordinates"]
        self.assertEqual(line[0], [-97.0, 30.0])
        start = self.geo["features"][1]["geometry"]["coordinates"]
        self.assertEqual(start, [-97.0, 30.0])

    def test_fuel_stops_are_numbered(self):
        stops = [f["properties"] for f in self.geo["features"] if f["properties"]["kind"] == "fuel_stop"]
        self.assertEqual([s["stop_number"] for s in stops], [1, 2])
        self.assertEqual(stops[1]["name"], "Station 2")


class SimplifyTests(SimpleTestCase):
    def test_long_route_is_reduced_and_keeps_both_ends(self):
        coords = [(i * 0.001, -97.0) for i in range(30000)]
        simplified = simplify(coords, max_points=1500)
        self.assertLessEqual(len(simplified), 1501)
        self.assertEqual(simplified[0], coords[0])
        self.assertEqual(simplified[-1], coords[-1])

    def test_short_route_is_unchanged(self):
        self.assertEqual(simplify(ROUTE, max_points=1500), ROUTE)


FAKE_PLAN = {
    "start": {"query": "Austin, TX"}, "finish": {"query": "Kansas City, KS"},
    "distance_miles": 550.0, "total_gallons": 55.0, "total_fuel_cost": 171.9,
    "fuel_stops": STOPS, "map": build_route_geojson(ROUTE, ORIGIN, DEST, STOPS),
}


@mock.patch("stations.views.plan_trip", return_value=FAKE_PLAN)
class MapViewTests(SimpleTestCase):
    def test_json_response_includes_map_and_map_url(self, _plan):
        data = self.client.get("/api/route/", {"start": "Austin, TX", "finish": "Kansas City, KS"}).json()
        self.assertEqual(data["map"]["type"], "FeatureCollection")
        self.assertIn("/api/route/map/?", data["map_url"])

    def test_map_page_renders(self, _plan):
        response = self.client.get("/api/route/map/", {"start": "Austin, TX", "finish": "Kansas City, KS"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "leaflet")
        self.assertContains(response, "Station 2")
        self.assertContains(response, 'id="route-geojson"')

    def test_map_page_without_params_is_400(self, _plan):
        self.assertEqual(self.client.get("/api/route/map/").status_code, 400)