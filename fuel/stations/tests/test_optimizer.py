"""Tests for the fuel stop optimizer.

Every expected value here was computed by hand, following the greedy rule:
  - If a CHEAPER station is within range, buy just enough fuel to reach it.
  - Otherwise, fill the tank and go to the cheapest station within range.
Vehicle: 500-mile range, 10 mpg -> 50-gallon tank. Tank starts empty.
"""
from django.test import SimpleTestCase

from stations.services.optimizer import InfeasibleRouteError, Stop, plan_fuel_stops

RANGE, MPG = 500, 10


def purchases(plan):
    """(mile, gallons) of each purchase, rounded, for easy comparison."""
    return [(p.stop.mile, round(p.gallons, 6)) for p in plan.purchases]


class OptimizerTests(SimpleTestCase):
    def test_short_trip_single_purchase(self):
        # 300 miles -> 30 gallons at $3.00
        plan = plan_fuel_stops([Stop(0, 3.00)], total_miles=300, max_range_miles=RANGE, mpg=MPG)
        self.assertEqual(purchases(plan), [(0, 30)])
        self.assertAlmostEqual(plan.total_cost, 90.00)

    def test_buys_only_enough_to_reach_a_cheaper_station(self):
        # mile 0 ($4): $3 at mile 200 is cheaper -> buy 20 gal, just enough to get there
        # mile 200 ($3): nothing cheaper in range -> fill up (50 gal), go to cheapest in range (600)
        # mile 600 ($5): arrive with 10 gal; $3.50 at 900 is cheaper -> buy 20 more
        # mile 900 ($3.50): destination in range -> buy the 10 gal needed
        stops = [Stop(0, 4.00), Stop(200, 3.00), Stop(600, 5.00), Stop(900, 3.50)]
        plan = plan_fuel_stops(stops, total_miles=1000, max_range_miles=RANGE, mpg=MPG)
        self.assertEqual(purchases(plan), [(0, 20), (200, 50), (600, 20), (900, 10)])
        self.assertAlmostEqual(plan.total_cost, 80 + 150 + 100 + 35)

    def test_skips_expensive_station_when_a_cheaper_one_is_reachable(self):
        # From mile 0, $3 at mile 450 is reachable -> the $5 station at mile 100 is never used
        stops = [Stop(0, 4.00), Stop(100, 5.00), Stop(450, 3.00)]
        plan = plan_fuel_stops(stops, total_miles=800, max_range_miles=RANGE, mpg=MPG)
        self.assertEqual(purchases(plan), [(0, 45), (450, 35)])

    def test_destination_exactly_at_max_range(self):
        plan = plan_fuel_stops([Stop(0, 3.00)], total_miles=500, max_range_miles=RANGE, mpg=MPG)
        self.assertEqual(purchases(plan), [(0, 50)])

    def test_total_gallons_always_equals_distance_over_mpg(self):
        # Many stations with varying prices: whatever the plan, fuel bought = fuel burned
        stops = [Stop(m, 3 + (m % 7) / 10) for m in range(0, 2800, 90)]
        plan = plan_fuel_stops(stops, total_miles=2800, max_range_miles=RANGE, mpg=MPG)
        self.assertAlmostEqual(plan.total_gallons, 280)
        self.assertTrue(all(p.gallons > 0 for p in plan.purchases))  # no empty purchases

    def test_gap_longer_than_range_is_infeasible(self):
        with self.assertRaises(InfeasibleRouteError):
            plan_fuel_stops([Stop(0, 3.00), Stop(700, 3.00)], total_miles=1000, max_range_miles=RANGE, mpg=MPG)

    def test_empty_tank_without_station_at_origin_is_infeasible(self):
        with self.assertRaises(InfeasibleRouteError):
            plan_fuel_stops([Stop(50, 3.00)], total_miles=300, max_range_miles=RANGE, mpg=MPG)

    def test_stops_out_of_order_are_sorted(self):
        stops = [Stop(450, 3.00), Stop(0, 4.00), Stop(100, 5.00)]
        plan = plan_fuel_stops(stops, total_miles=800, max_range_miles=RANGE, mpg=MPG)
        self.assertEqual(purchases(plan), [(0, 45), (450, 35)])