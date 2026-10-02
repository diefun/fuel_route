# Fuel Route API

A Django API that takes a start and finish location in the USA and returns the route, the most cost-effective places to fuel up along the way, and the total fuel cost.

Vehicle assumptions from the assignment: 500-mile range and 10 miles per gallon (so a 50-gallon tank).

## Quick start

Requires Python 3.12+ (Django 6.1).

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cd fuel
python manage.py migrate
python manage.py import_fuel_prices   # loads and geocodes the stations (a few seconds)
python manage.py runserver
```

All the data the import needs is in `data/raw/`, so it runs offline and gives the same result every time.

## Usage

```
GET  /api/route/?start=Dallas, TX&finish=Chicago, IL
POST /api/route/   {"start": "Dallas, TX", "finish": "Chicago, IL"}
GET  /api/route/map/?start=Dallas, TX&finish=Chicago, IL     -> HTML page with the map
```

Locations can be written as `City, ST` or as `lat,lon` (e.g. `32.77,-96.79`).

The JSON response includes the map as GeoJSON (`map`) and a link to an HTML page that draws it (`map_url`). The map page reuses the cached plan, so opening it doesn't call the routing API again.

Example response (values are illustrative):

```json
{
  "start": {"query": "Dallas, TX", "latitude": 32.794176, "longitude": -96.765503},
  "finish": {"query": "Chicago, IL", "latitude": 41.837551, "longitude": -87.681844},
  "distance_miles": 925.4,
  "total_gallons": 92.54,
  "total_fuel_cost": 301.77,
  "fuel_stops": [
    {
      "name": "PILOT TRAVEL CENTER #1243",
      "city": "Dallas",
      "state": "TX",
      "latitude": 32.794176,
      "longitude": -96.765503,
      "mile_marker": 0.0,
      "price_per_gallon": 3.199,
      "gallons": 21.3,
      "cost": 68.14
    }
  ],
  "map": {
    "type": "FeatureCollection",
    "features": ["route (LineString)", "start and finish (Points)", "fuel stops (Points)"]
  },
  "map_url": "http://localhost:8000/api/route/map/?start=Dallas%2C+TX&finish=Chicago%2C+IL",
  "meta": {"routing_api_calls": 1, "cached": false, "elapsed_ms": 412.6}
}
```

Error responses use the status code that matches the problem:

| Status | When |
|---|---|
| 400 | Missing parameters, invalid JSON, or a location that can't be found or is outside the USA |
| 422 | The input is valid but the trip is impossible (a stretch longer than 500 miles with no stations) |
| 502 | The routing provider failed or timed out |

## How it works

### 1. Exploring the fuel price data

Before writing any Django code I explored the CSV in a notebook (`notebooks/01_explore_fuel_prices.ipynb`). The main findings:

- 8,151 rows, no null values, and no coordinates: only addresses like "I-44, EXIT 283 & US-69", which can't be geocoded reliably.
- 620 rows are Canadian stations (ON, AB, BC, ...). I excluded them, since routes are US-only and those prices belong to a different market.
- Many stations appear more than once, sometimes with different prices. In most cases the price is the same (median difference $0.00), so I keep the lowest price per station, which is what a driver would actually pay.
- The `City` column has trailing whitespace, which has to be stripped before matching.

That leaves **6,626 unique US stations**.

### 2. Geocoding the stations (once, at import time)

Since the addresses aren't usable, I geocode at city level using the US Census Gazetteer files, which are free and can be used offline. There are 3,813 unique city/state pairs to resolve. I explored the gazetteer format in `notebooks/02_geocode_gazetteer.ipynb`, worked out the matching in `notebooks/03_merge_fuel_and_gaz.ipynb`, and the final logic lives in `stations/services/geo.py`.

- **Census Places** covers incorporated cities, towns and CDPs.
- **County Subdivisions** is used as a second source for stations that didn't match. It covers New England and New York towns and Pennsylvania townships, which aren't "places" for the Census.
- City names are normalized on both sides before matching: uppercase, no punctuation, no spaces ("Mc Lean" vs "McLean", "De Forest" vs "DeForest"), and SAINT→ST, SAINTE→STE, FORT→FT, MOUNT→MT. Census suffixes like "city", "town" or "CDP" are removed from the gazetteer side.
- When two gazetteer entries end up with the same key in the same state, I prefer the incorporated place and then the larger land area.
- One alias for "Town of Pecos city" (TX), which matters because Pecos has 9 stations on I-20. I checked the other names with a "Town of / City of" prefix, and none of them has stations, so a general rule wasn't worth it.

Result: **96.0% of stations geocoded** (94.4% from Places, 1.6% from County Subdivisions). The remaining 263 are mostly unincorporated communities. They are evenly spread except in Virginia (15.7% missing), where many truck stops sit in unincorporated places along I-95 and I-81. Coverage on the main corridors is still dense.

Stations without coordinates are kept in the database but ignored when planning routes.

### 3. Routing: one external call per trip

The route comes from the public [OSRM](https://project-osrm.org/) server (free, no API key), with one call per trip. User locations are resolved with the same gazetteer, so a request makes no geocoding calls. Results are cached, so repeating a trip makes zero external calls (`meta.routing_api_calls` shows this).

### 4. Finding stations along the route

`stations/services/route_stations.py`:

- All geocoded stations are loaded once per process into a KD-tree (a spatial index), so finding stations near a route takes milliseconds instead of comparing against every station.
- Coordinates are converted to 3D (x, y, z in miles) because the KD-tree uses straight-line distance. At a few miles, that's practically the same as the distance over the Earth's surface.
- The route is densified to points every mile, because OSRM can leave several miles between points on straight highways.
- A station is considered "on the route" if it's within 10 miles of it. That margin also absorbs the city-level precision of the coordinates.
- Each station gets a mile marker: its position along the route, rescaled to the distance reported by OSRM.

### 5. Choosing where to fuel up

`stations/services/optimizer.py` is a pure function with no Django dependencies, so it's easy to test. It's a greedy algorithm for the classic "gas station problem", which is optimal for a fixed route:

- At each station, look at all the stations within range (500 miles).
- **If one of them is cheaper**, buy just enough fuel to reach the first cheaper one.
- **Otherwise** (the current station is the cheapest within range), fill the tank and go to the cheapest station within range.
- The destination is treated as a station with price 0, so near the end the truck buys only what it needs to arrive.

### 6. The map

`stations/services/geojson.py` builds a GeoJSON FeatureCollection, the standard format for map data, so any map library or tool (like [geojson.io](https://geojson.io)) can draw it directly:

- The route as a `LineString`, simplified to at most 1,500 points. A coast-to-coast route from OSRM can have tens of thousands of points, which would make the response several MB, and on a map it looks the same. The simplification is only for drawing: station matching uses the full route.
- Start, finish and each fuel stop as `Point`s, with the stop details as properties.
- Coordinates in GeoJSON's `[longitude, latitude]` order. That's the opposite of the rest of the project, so the conversion happens in this one place and has its own test.

The HTML page (`/api/route/map/`) draws the GeoJSON with [Leaflet](https://leafletjs.com/) over OpenStreetMap tiles, with the list of stops and the total cost on the side.

### 7. Caching

Plans (including the map) are cached with Django's cache framework (in-memory). The cache key uses the resolved coordinates rounded to 4 decimals (about 10 meters), so "Dallas, TX", "dallas, tx" and the equivalent `lat,lon` share the same entry. The import command clears the cache and the station index, so new prices take effect immediately.

## Assumptions

- **The truck leaves with an empty tank** and fills up at the station closest to the origin (mile 0). This way the total cost covers the whole trip and always equals distance / 10 × the prices paid. Starting with a full tank would make a 400-mile trip cost $0.
- **"Optimal" means the lowest total cost**, not the fewest stops. On long trips this can mean several partial fill-ups. For example, leaving New York the algorithm buys 1 gallon at the first station just to reach a cheaper one 10 miles later: correct by cost, but not what a driver would do.
- **Stations are drawn at the center of their city**, since their coordinates are city-level. On the map, some stops can look a few miles off the route.
- **The detour to reach a station isn't added to the trip distance.** Stations are at most 10 miles from the route, and their coordinates are city-level anyway.
- **Duplicated stations use their lowest price.**

## Tests

```bash
cd fuel
python manage.py test stations
```

There are tests for each layer:

- `test_geo.py`: name normalization, suffix removal and location parsing.
- `test_import_command.py`: the import command against small fixture files covering every rule (duplicates, Canadian rows, County Subdivisions, the Pecos alias, an unmatched town, duplicated gazetteer keys, idempotency).
- `test_routing.py`: the OSRM client with mocked responses (unit conversion, lat/lon order, error codes, timeouts, input validation).
- `test_route_stations.py`: distance helpers, densification and station matching on a synthetic route.
- `test_optimizer.py`: the fuel stop algorithm, with expected values computed by hand.
- `test_planner.py`: the full flow with the route mocked, including the cache.
- `test_views.py`: input handling and HTTP status codes.
- `test_map.py`: the GeoJSON structure (including the `[lon, lat]` order), route simplification and the HTML map page.

No test calls an external service.

## Project structure

```
data/
  raw/            fuel prices CSV and Census Gazetteer files (committed)
  interim/        files generated by the notebooks (not committed)
notebooks/
  01_explore_fuel_prices.ipynb   cleaning and duplicates
  02_geocode_gazetteer.ipynb     Census Gazetteer format and suffixes
  03_merge_fuel_and_gaz.ipynb    matching stations to coordinates
fuel/
  manage.py
  config/         Django project settings
  stations/
    management/commands/import_fuel_prices.py
    services/
      geo.py              normalization, gazetteer, location parsing
      routing.py          OSRM client
      route_stations.py   spatial index and stations along a route
      optimizer.py        fuel stop algorithm
      planner.py          orchestration and caching
      geojson.py          map output (GeoJSON)
    templates/stations/map.html
    views.py
    tests/
```

## What I would improve with more time

- **Geocode the remaining 4%** with Nominatim (OpenStreetMap) at import time, rate-limited and cached. It would mostly help in Virginia.
- **Penalize the number of stops** in the optimizer (or require a minimum purchase per stop), since drivers usually prefer fewer, larger fill-ups over saving a few cents.
- **Use exact station coordinates** if a source with them were available, and include the detour distance in the calculation.
- **Use Redis for the cache**, so it's shared between processes and survives restarts. It's only a settings change.
- **Run my own OSRM instance** in production instead of the public demo server, which isn't meant for heavy use.

## Data sources

- Fuel prices: CSV provided with the assignment.
- [US Census Gazetteer Files](https://www.census.gov/geographies/reference-files/time-series/geo/gazetteer-files.html), 2026: Places and County Subdivisions.
- Routing: [OSRM](https://project-osrm.org/) public API.
- Map tiles: [OpenStreetMap](https://www.openstreetmap.org/).