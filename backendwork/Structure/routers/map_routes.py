from fastapi import APIRouter, HTTPException

from services.map_service import get_route_distance


router = APIRouter(
    prefix="/maps",
    tags=["Maps"]
)


# ==================================================
# GET ROAD DISTANCE
# ==================================================
@router.get("/distance")
def get_distance(
    pickup: str,
    destination: str
):
    try:
        distance = get_route_distance(
            pickup,
            destination
        )

        return {
            "pickup": pickup,
            "destination": destination,
            "distance_km": distance
        }

    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e)
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Could not calculate route distance"
        )