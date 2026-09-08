import requests


NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"


def geocode_location(location: str):
    """
    Convert a human-readable address into latitude/longitude.
    """

    params = {
        "q": location,
        "format": "json",
        "limit": 1
    }

    headers = {
        "User-Agent": "FarmDirect-SIH/1.0"
    }

    response = requests.get(
        NOMINATIM_URL,
        params=params,
        headers=headers,
        timeout=10
    )

    response.raise_for_status()

    results = response.json()

    if not results:
        raise ValueError(
            f"Could not find location: {location}"
        )

    return {
        "latitude": float(results[0]["lat"]),
        "longitude": float(results[0]["lon"])
    }


def get_route_distance(
    pickup_location: str,
    delivery_location: str
):
    """
    Get road distance between pickup and delivery locations.
    Returns distance in kilometers.
    """

    pickup = geocode_location(pickup_location)
    delivery = geocode_location(delivery_location)

    # OSRM expects:
    # longitude,latitude
    coordinates = (
        f"{pickup['longitude']},{pickup['latitude']};"
        f"{delivery['longitude']},{delivery['latitude']}"
    )

    url = f"{OSRM_URL}/{coordinates}"

    params = {
        "overview": "false"
    }

    response = requests.get(
        url,
        params=params,
        timeout=10
    )

    response.raise_for_status()

    data = response.json()

    if data.get("code") != "Ok":
        raise ValueError(
            "Could not calculate route"
        )

    distance_meters = data["routes"][0]["distance"]

    distance_km = distance_meters / 1000

    return round(distance_km, 2)