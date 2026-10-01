from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from stations.models import FuelStation

FIXTURES = Path(__file__).parent / "fixtures"


class ImportFuelPricesCommandTests(TestCase):
    """Runs the import against tiny fixture files that cover every rule:

    - Dallas, TX: duplicated ID (keeps the lowest price) + trailing spaces in City
    - Toronto, ON: Canadian row, must be excluded
    - De Forest, WI: space difference vs Census "DeForest"
    - St. Louis, MO: dots / SAINT normalization
    - Darien, CT: only in County Subdivisions (cousub)
    - Pecos, TX: needs the alias ("Town of Pecos city")
    - Ruther Glen, VA: unincorporated, not found anywhere
    - Springfield, IL: duplicated gazetteer key (city vs CDP), must pick the city
    """

    def run_import(self):
        out = StringIO()
        call_command(
            "import_fuel_prices",
            csv=str(FIXTURES / "fuel_prices_sample.csv"),
            places=str(FIXTURES / "gazetteer_places_sample.txt"),
            cousub=str(FIXTURES / "gazetteer_cousub_sample.txt"),
            stdout=out,
        )
        return out.getvalue()

    def test_counts(self):
        self.run_import()
        self.assertEqual(FuelStation.objects.count(), 7)  # 8 IDs - 1 Canadian
        self.assertFalse(FuelStation.objects.filter(state="ON").exists())

    def test_duplicates_keep_lowest_price(self):
        self.run_import()
        dallas = FuelStation.objects.get(opis_id=1)
        self.assertEqual(float(dallas.price), 3.20)
        self.assertEqual(dallas.city, "Dallas")  # trailing spaces stripped

    def test_geocode_sources(self):
        self.run_import()
        source = dict(FuelStation.objects.values_list("opis_id", "geocode_source"))
        self.assertEqual(source[1], "place")    # Dallas
        self.assertEqual(source[3], "place")    # De Forest -> DeForest
        self.assertEqual(source[4], "place")    # St. Louis
        self.assertEqual(source[5], "cousub")   # Darien
        self.assertEqual(source[6], "place")    # Pecos (alias)
        self.assertEqual(source[7], "")         # Ruther Glen, not found

    def test_unmatched_station_is_saved_without_coordinates(self):
        self.run_import()
        ruther_glen = FuelStation.objects.get(opis_id=7)
        self.assertIsNone(ruther_glen.latitude)
        self.assertIsNone(ruther_glen.longitude)

    def test_duplicate_gazetteer_key_prefers_incorporated_place(self):
        self.run_import()
        springfield = FuelStation.objects.get(opis_id=8)
        self.assertAlmostEqual(springfield.latitude, 39.78325, places=4)

    def test_is_idempotent(self):
        self.run_import()
        self.run_import()
        self.assertEqual(FuelStation.objects.count(), 7)
