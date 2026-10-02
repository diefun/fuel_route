import requests
from django.test import SimpleTestCase
from stations.services.planner import plan_trip
from stations.services.routing import Route, RoutingError, get_route
from unittest import mock


FAKE_OSRM = {
    "code": "Ok",
    "routes": [{
        "distance": 160934.4,   # 100 miles in meters
        "duration": 7200,       # 2 hours in seconds
        "geometry": {"coordinates": [[-86.0, 33.0], [-85.9, 33.1], [-85.8, 33.2]]},  # [lon, lat]
    }],
}


class GetRouteTests(SimpleTestCase):
    @mock.patch("stations.services.routing.requests.get")
    def test_success_converts_units_and_coord_order(self, mock_get):
        mock_get.return_value.json.return_value = FAKE_OSRM
        mock_get.return_value.raise_for_status.return_value = None

        route = get_route((33.0, -86.0), (33.2, -85.8))

        self.assertIsInstance(route, Route)
        self.assertAlmostEqual(route.distance_miles, 100, places=2)
        self.assertAlmostEqual(route.duration_hours, 2)
        self.assertEqual(route.coords[0], (33.0, -86.0))  # (lat, lon), inverse of OSRM's (lon, lat)
        self.assertEqual(len(route.coords), 3)
        mock_get.assert_called_once()
        
    @mock.patch("stations.services.routing.requests.get")
    def test_osrm_error_code(self, mock_get):
        mock_get.return_value.json.return_value = {"code": "NoRoute", "message": "No route found"}
        mock_get.return_value.raise_for_status.return_value = None

        with self.assertRaises(RoutingError):
            get_route((33.0, -86.0), (33.2, -85.8))

    @mock.patch("stations.services.routing.requests.get", side_effect=requests.Timeout)
    def test_timeout(self, mock_get):
        with self.assertRaises(RoutingError):
            get_route((33.0, -86.0), (33.2, -85.8))

    @mock.patch("stations.services.routing.requests.get")
    def test_invalid_latitude_does_not_call_osrm(self, mock_get):
        with self.assertRaises(RoutingError):
            get_route((91.0, -74.0), (34.0, -118.0))
        mock_get.assert_not_called()