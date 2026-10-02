import csv
import re

from django.conf import settings
from functools import lru_cache


SUFFIXES = [
    " city and borough", " CDP", " city", " town", " village", " borough",
    " comunidad", " urbana", " (balance)", " municipality", " government",
    " County", " county", " City", " Princeton", " corporation", " township",
    " plantation"
]


def strip_suffix(name):
    for suffix in sorted(SUFFIXES, key=len, reverse=True):
        if name.endswith(suffix):
    
            return name[: -len(suffix)]
    
    return name


REPLACEMENTS = [(r"\bSAINT\b", "ST"), (r"\bFORT\b", "FT"), (r"\bMOUNT\b", "MT")]


def normalize_place_name(name):
    name = name.upper().replace(".", "").replace("'", "").replace("-", " ")
    
    for pattern, repl in REPLACEMENTS:
        name = re.sub(pattern, repl, name)
    
    return "".join(name.split())


ALIASES = {
    ("PECOS", "TX"): "TOWNOFPECOS",
    ("BOISE", "ID"): "BOISECITY",
}


CA = {'ON','AB','BC','MB','SK','YT','QC','NS','NB'}


def load_gazetteer(path):
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
        
        return gazetteer


class LocationError(ValueError):
    pass


US_STATES = {
    "AL", "AR", "AZ", "CA", "CO", "CT", "DC", "DE", "FL", "GA", "IA", "ID", "IL", "IN",
    "KS", "KY", "LA", "MA", "MD", "ME", "MI", "MN", "MO", "MS", "MT", "NC", "ND", "NE",
    "NH", "NJ", "NM", "NV", "NY", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX",
    "UT", "VA", "VT", "WA", "WI", "WV", "WY",
}


@lru_cache(maxsize=1)
def get_places_index():
    return load_gazetteer(settings.FUEL_DATA["GAZETTEER_PLACES"])


@lru_cache(maxsize=1)
def get_cousub_index():
    return load_gazetteer(settings.FUEL_DATA["GAZETTEER_COUSUB"])


def parse_location(raw: str) -> tuple[float, float]:
    """Parse 'lat,lon' (e.g. '32.77,-96.79') or 'City, ST' (e.g. 'Dallas, TX') into (lat, lon)."""
    parts = [p.strip() for p in (raw or "").rsplit(",", 1)]
    
    if len(parts) != 2 or not all(parts):
        raise LocationError(f"Could not parse '{raw}'. Use 'City, ST' or 'lat,lon'.")
    first, second = parts

    try:
        lat, lon = float(first), float(second)
    except ValueError:
        pass
    else:
        if not (24 <= lat <= 50 and -125 <= lon <= -66):
            raise LocationError(f"'{raw}' is outside the continental USA.")
        
        return lat, lon

    state = second.upper()
    
    if state not in US_STATES:
        raise LocationError(f"'{second}' is not a US state code.")

    key = normalize_place_name(first)
    key = ALIASES.get((key, state), key)

    coords = get_places_index().get((key, state)) or get_cousub_index().get((key, state))
    
    if coords is None:
        raise LocationError(f"Could not find '{first}, {state}'. Use 'City, ST' or 'lat,lon'.")
    
    return coords