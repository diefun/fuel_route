# fuel/tests/test_geo.py
from django.test import SimpleTestCase

from stations.services.geo import normalize_place_name, strip_suffix


class NormalizePlaceNameTests(SimpleTestCase):
    def test_removes_spaces(self):
        self.assertEqual(normalize_place_name("De Forest"), "DEFOREST")

    def test_saint_and_dots(self):
        self.assertEqual(normalize_place_name("St. Louis"), "STLOUIS")
        self.assertEqual(normalize_place_name("Saint Louis"), "STLOUIS")

    def test_does_not_touch_inside_words(self):
        self.assertEqual(normalize_place_name("Fortuna"), "FORTUNA")

    def test_trailing_whitespace(self):
        self.assertEqual(normalize_place_name("Effingham        "), "EFFINGHAM")


class StripSuffixTests(SimpleTestCase):
    def test_simple_suffix(self):
        self.assertEqual(strip_suffix("Dallas city"), "Dallas")

    def test_multi_word_suffix(self):
        self.assertEqual(strip_suffix("Juneau city and borough"), "Juneau")