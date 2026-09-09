from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from fastapi import HTTPException
from jose import jwt, JWTError
from config import SECRET_KEY
from services.map_service import get_route_details

VEHICLES = [(100, 'Small Pickup', '10.00'), (500, 'Mini Truck', '15.00'),
            (2000, 'Medium Truck', '20.00'), (20000, 'Large Truck', '25.00')]

def money(value):
    return Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def make_quote(product, quantity, destination, buyer_id):
    if not product.is_active or quantity > product.quantity:
        raise HTTPException(409, 'Product is unavailable or has insufficient stock')
    if product.unit.lower() not in {'kg','kgs','kilogram','kilograms'}:
        raise HTTPException(409, 'Farmer must convert this listing to kilograms before delivery')
    if not product.location or product.location.strip().lower() == 'unknown':
        raise HTTPException(422, 'Product needs a valid pickup address')
    if not destination or destination.strip().lower() == 'unknown':
        raise HTTPException(422, 'A valid delivery address is required')
    vehicle = next((v for v in VEHICLES if quantity <= v[0]), None)
    if vehicle is None:
        raise HTTPException(422, 'Maximum delivery weight is 20000 kg; split this order')
    route = get_route_details(product.location, destination)
    distance = money(str(route['distance_km']))
    cost = money(quantity * product.price_per_unit)
    transport = money(distance * Decimal(vehicle[2]))
    quote = {'product_id':product.id, 'product_name':product.name, 'quantity':str(quantity), 'unit':'kg',
        'price_per_unit':str(product.price_per_unit), 'product_cost':str(cost),
        'pickup_location':product.location, 'destination':destination,
        'distance_km':str(distance), 'vehicle_type':vehicle[1], 'vehicle_rate_per_km':vehicle[2],
        'transport_cost':str(transport), 'estimated_total':str(cost + transport),
        'pickup':route['pickup'], 'delivery':route['destination']}
    token = jwt.encode({**quote, 'sub':str(buyer_id), 'type':'delivery_quote', 'jti':str(uuid4()),
        'exp':datetime.now(timezone.utc) + timedelta(minutes=15)}, SECRET_KEY, algorithm='HS256')
    return {**quote, 'quote_token':token, 'valid_for_seconds':900,
        'attribution':'© OpenStreetMap contributors; route by OSRM'}

def verify_quote(token, product, order_in, destination, buyer_id):
    try:
        q = jwt.decode(token, SECRET_KEY, algorithms=['HS256'], options={'require_exp':True, 'require_sub':True})
        matches = (q.get('type') == 'delivery_quote' and q['sub'] == str(buyer_id)
            and q['product_id'] == product.id and Decimal(q['quantity']) == order_in.quantity
            and q['destination'] == destination and q['pickup_location'] == product.location
            and q['product_name'] == product.name and Decimal(q['price_per_unit']) == product.price_per_unit
            and product.unit.lower() in {'kg','kgs','kilogram','kilograms'})
        if not matches:
            raise ValueError()
        return q
    except (JWTError, KeyError, ValueError, TypeError):
        raise HTTPException(409, 'Quote expired or listing/order changed; request a new estimate')
