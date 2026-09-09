"""CHANGED: bounded caches, provider error types, and serialized geocoding.
Public Nominatim: run ONE worker; use a managed provider for larger deployment.
"""
import os
import time
import math
from collections import OrderedDict
from threading import Lock
import requests

NOMINATIM_URL = os.getenv('NOMINATIM_URL', 'https://nominatim.openstreetmap.org/search')
OSRM_URL = os.getenv('OSRM_URL', 'https://router.project-osrm.org/route/v1/driving')
_lock = Lock()
_cache = OrderedDict()
_last_geocode = 0.0

class LocationNotFound(ValueError):
    pass

class MapUnavailable(RuntimeError):
    pass

def _get(url, **kwargs):
    try:
        response = requests.get(url, timeout=(3, 10), **kwargs)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise MapUnavailable('Map service is temporarily unavailable; try again') from exc

def _cached(key, fetch):
    # The same lock prevents duplicate cache misses across concurrent requests.
    with _lock:
        entry = _cache.get(key)
        if entry and time.monotonic() - entry[0] < 86400:
            _cache.move_to_end(key)
            return entry[1]
        result = fetch()
        _cache[key] = (time.monotonic(), result)
        _cache.move_to_end(key)
        while len(_cache) > 1000:
            _cache.popitem(last=False)
        return result

def geocode_location(location):
    location = location.strip()
    if not location:
        raise LocationNotFound('Location cannot be blank')
    def fetch():
        global _last_geocode
        delay = 1.05 - (time.monotonic() - _last_geocode)
        if delay > 0:
            time.sleep(delay)
        _last_geocode = time.monotonic()
        results = _get(NOMINATIM_URL, params={'q':location, 'format':'json', 'limit':1},
            headers={'User-Agent':os.getenv('MAP_USER_AGENT', 'FarmDirect/2.0')})
        if results == []:
            raise LocationNotFound(f'Could not find location: {location}')
        try:
            lat, lon = float(results[0]['lat']), float(results[0]['lon'])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError()
            return {'latitude':round(lat, 7), 'longitude':round(lon, 7),
                    'display_name':str(results[0].get('display_name', location))}
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise MapUnavailable('Map provider returned invalid coordinates') from exc
    return dict(_cached(('geo', location.casefold()), fetch))

def get_route_details(pickup_location, delivery_location):
    pickup = geocode_location(pickup_location)
    delivery = geocode_location(delivery_location)
    coordinates = f"{pickup['longitude']},{pickup['latitude']};{delivery['longitude']},{delivery['latitude']}"
    def fetch():
        data = _get(f'{OSRM_URL}/{coordinates}', params={'overview':'false'})
        if isinstance(data, dict) and data.get('code') == 'NoRoute':
            raise LocationNotFound('No driving route was found')
        try:
            if data['code'] != 'Ok':
                raise ValueError()
            distance = float(data['routes'][0]['distance']) / 1000
            if not math.isfinite(distance) or distance < 0:
                raise ValueError()
            return round(distance, 2)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise MapUnavailable('Map provider returned an invalid route') from exc
    return {'distance_km':_cached(('route',coordinates), fetch), 'pickup':pickup, 'destination':delivery}

def get_route_distance(pickup_location, delivery_location):
    return get_route_details(pickup_location, delivery_location)['distance_km']
