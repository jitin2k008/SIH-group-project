import logging
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError
from routers import auth_routes, product_routes, order_routes, delivery_routes, map_routes
from services.map_service import LocationNotFound, MapUnavailable

logging.basicConfig(level=logging.INFO)
app = FastAPI(title='FarmDirect API', version='2.0.0')
# CHANGED: migrations run explicitly, never during application import.
origins = [s.strip() for s in os.getenv('CORS_ORIGINS', '').split(',') if s.strip()]
if origins:
    app.add_middleware(CORSMiddleware, allow_origins=origins,
        allow_methods=['GET','POST','PUT','PATCH','DELETE'], allow_headers=['Authorization','Content-Type'])
for module in [auth_routes, product_routes, order_routes, delivery_routes, map_routes]:
    app.include_router(module.router)

@app.exception_handler(LocationNotFound)
async def invalid_location(request: Request, exc: LocationNotFound):
    return JSONResponse(status_code=422, content={'detail':str(exc)})

@app.exception_handler(MapUnavailable)
async def unavailable_maps(request: Request, exc: MapUnavailable):
    logging.getLogger(__name__).warning('Map provider failed: %s', type(exc.__cause__).__name__)
    return JSONResponse(status_code=503, content={'detail':str(exc)})

@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    logging.getLogger(__name__).error('Database operation failed: %s', type(exc).__name__)
    return JSONResponse(status_code=503, content={'detail':'Database operation failed; try again'})

@app.get('/')
def root():
    return {'message':'FarmDirect API is running'}
