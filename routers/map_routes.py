from typing import Annotated
from fastapi import APIRouter, Depends, Query
import auth, models
from services.map_service import get_route_distance

router = APIRouter(prefix='/maps', tags=['Maps'])

@router.get('/distance')
def get_distance(pickup: Annotated[str, Query(min_length=1, max_length=250)],
                 destination: Annotated[str, Query(min_length=1, max_length=250)],
                 user: models.User = Depends(auth.get_current_user)):
    return {'pickup':pickup, 'destination':destination,
            'distance_km':get_route_distance(pickup, destination),
            'attribution':'© OpenStreetMap contributors; route by OSRM'}
