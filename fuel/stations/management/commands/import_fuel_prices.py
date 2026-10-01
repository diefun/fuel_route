import csv
from decimal import Decimal
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from stations.models import FuelStation
from stations.services.geo import ALIASES, CA, strip_suffix, normalize_place_name


class Command(BaseCommand):
    help = "Import fuel prices from CSV and geocode stations with the Census gazetteer."

    def add_arguments(self, parser):
        parser.add_argument("--csv", default=settings.FUEL_DATA["PRICES_CSV"])
        parser.add_argument("--places", default=settings.FUEL_DATA["GAZETTEER_PLACES"])
        parser.add_argument("--cousub", default=settings.FUEL_DATA["GAZETTEER_COUSUB"])

    def handle(self, *args, **options):
        stations = self.read_stations(options["csv"])
        places = self.load_gazetteer(options["places"])
        cousub = self.load_gazetteer(options["cousub"])
        self.geocode(stations, places, cousub)
        self.save(stations)
        self.stdout.write(self.style.SUCCESS("Done."))

    def read_stations(self, path):
        self.stdout.write(f"Reading {path}")

        with open(path, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            stations = {}

            for row in reader:
                if row["State"] in CA:
                    continue

                station = {
                    "opis_id": int(row["OPIS Truckstop ID"]),
                    "name": row["Truckstop Name"].strip(),
                    "address": row["Address"].strip(),
                    "city": row["City"].strip(),
                    "state": row["State"].strip(),
                    "price": Decimal(row["Retail Price"]),
                }

                current = stations.get(station["opis_id"])
                
                if current is None or station["price"] < current["price"]:
                    stations[station["opis_id"]] = station

        self.stdout.write(f"{len(stations)} stations read")
        
        return stations
    
    def load_gazetteer(self, path):
        self.stdout.write(f"Loading {path}")
        best = {}

        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f, delimiter="|")
            reader.fieldnames = [h.strip() for h in reader.fieldnames]

            for row in reader:
                key = (normalize_place_name(strip_suffix(row["NAME"].strip())), row["USPS"].strip())
                rank = (row["FUNCSTAT"].strip() == "A", int(row["ALAND"]))
                current = best.get(key)
                
                if current is None or rank > current[0]:
                    best[key] = (rank, float(row["INTPTLAT"]), float(row["INTPTLONG"].strip()))

        gazetteer = {key: (lat, lon) for key, (_, lat, lon) in best.items()}
        self.stdout.write(f"{len(gazetteer)} gazetteer entries loaded")
        
        return gazetteer

    def geocode(self, stations, places, cousub):
        self.stdout.write("Geocoding stations")
        places_count = 0
        cousub_count = 0
        none_count = 0

        for station in stations.values():
            key = (normalize_place_name(station["city"]), station["state"])

            if key in ALIASES:
                key = (ALIASES[key], station["state"])

            if places.get(key):
                station["latitude"], station["longitude"] = places[key]
                station["geocode_source"] = "place"
                places_count += 1
            elif cousub.get(key):
                station["latitude"], station["longitude"] = cousub[key]
                station["geocode_source"] = "cousub"
                cousub_count += 1
            else:
                station["latitude"], station["longitude"] = None, None
                station["geocode_source"] = ""
                none_count += 1

        self.stdout.write(f"{len(stations)} stations geocoded")
        self.stdout.write(f"{places_count} stations geocoded from gazetteer")
        self.stdout.write(f"{cousub_count} stations geocoded from cousub")
        self.stdout.write(f"{none_count} stations not geocoded")

    def save(self, stations):
        self.stdout.write("Saving stations to database")
        objects = [FuelStation(**station) for station in stations.values()]

        with transaction.atomic():
            FuelStation.objects.all().delete()

            FuelStation.objects.bulk_create(objects, batch_size=1000)

        self.stdout.write(f"{len(objects)} stations saved to database")
