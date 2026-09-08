from fastapi import FastAPI
from database import Base, engine

from routers import map_routes
from routers import product_routes
from routers import auth_routes
from routers import order_routes
from routers import delivery_routes

# Creates database tables if they don't exist yet.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="FarmDirect API")

app.include_router(map_routes.router)
app.include_router(delivery_routes.router)
app.include_router(auth_routes.router)
app.include_router(product_routes.router)
app.include_router(order_routes.router)


@app.get("/")
def root():
    return {"message": "FarmDirect API is running"}