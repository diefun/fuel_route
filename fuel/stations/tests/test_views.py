"""Tests for the HTTP layer of the API.

plan_trip is mocked: the planner already has its own tests. Here we only check what
the VIEW is responsible for: reading GET/POST input, validating it, and turning each
kind of error into the right HTTP status code.
"""
from unittest import mock

from django.test import SimpleTestCase

from stations.services.geo import LocationError
from stations.services.optimizer import InfeasibleRouteError
from stations.services.routing import RoutingError

URL = "/api/route/"
FAKE_PLAN = {"distance_miles": 925.4, "total_fuel_cost": 301.77, "fuel_stops": []}


@mock.patch("stations.views.plan_trip")
class RoutePlanViewTests(SimpleTestCase):
    # --- happy path -------------------------------------------------------------
    def test_get_returns_plan(self, mock_plan):
        mock_plan.return_value = FAKE_PLAN
        response = self.client.get(URL, {"start": "Dallas, TX", "finish": "Chicago, IL"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_fuel_cost"], FAKE_PLAN["total_fuel_cost"])
        self.assertIn("map_url", data)  # the view adds a link to the HTML map
        mock_plan.assert_called_once_with("Dallas, TX", "Chicago, IL")

    def test_post_json_returns_plan(self, mock_plan):
        mock_plan.return_value = FAKE_PLAN
        response = self.client.post(URL, {"start": "Dallas, TX", "finish": "Chicago, IL"},
                                    content_type="application/json")
        self.assertEqual(response.status_code, 200)
        mock_plan.assert_called_once_with("Dallas, TX", "Chicago, IL")

    # --- input validation (400) -------------------------------------------------
    def test_missing_finish(self, mock_plan):
        response = self.client.get(URL, {"start": "Dallas, TX"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())
        mock_plan.assert_not_called()

    def test_invalid_json_body(self, mock_plan):
        response = self.client.post(URL, "{not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        mock_plan.assert_not_called()

    # --- errors from the planner -> status codes ------------------------------------
    def test_unknown_location_is_400(self, mock_plan):
        mock_plan.side_effect = LocationError("Could not find 'Springfeld, IL'.")
        response = self.client.get(URL, {"start": "Springfeld, IL", "finish": "Chicago, IL"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Springfeld", response.json()["error"])

    def test_infeasible_route_is_422(self, mock_plan):
        mock_plan.side_effect = InfeasibleRouteError("Gap of 620 miles after mile 100.")
        response = self.client.get(URL, {"start": "A, TX", "finish": "B, TX"})
        self.assertEqual(response.status_code, 422)

    def test_routing_provider_failure_is_502(self, mock_plan):
        mock_plan.side_effect = RoutingError("OSRM timeout")
        response = self.client.get(URL, {"start": "Dallas, TX", "finish": "Chicago, IL"})
        self.assertEqual(response.status_code, 502)

    # --- HTTP method ----------------------------------------------------------------
    def test_other_methods_not_allowed(self, mock_plan):
        response = self.client.put(URL, {"start": "Dallas, TX", "finish": "Chicago, IL"},
                                   content_type="application/json")
        self.assertEqual(response.status_code, 405)