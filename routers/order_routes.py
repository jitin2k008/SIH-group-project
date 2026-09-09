from datetime import timedelta
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import auth, models, schemas
from config import RESERVATION_HOURS
from database import get_db
from services.common import commit, get_or_404
from services.orders import expired, release_stock
from services.pricing import verify_quote

router = APIRouter(prefix='/orders', tags=['Orders'])

@router.post('/', response_model=schemas.OrderOut, status_code=201)
def create_order(order_in: schemas.OrderCreate, db: Session = Depends(get_db),
                 user: models.User = Depends(auth.require_buyer)):
    destination = order_in.delivery_location or user.location
    product = get_or_404(db, models.Product, order_in.product_id, lock=True)
    q = verify_quote(order_in.quote_token, product, order_in, destination, user.id)
    existing = db.query(models.Order).filter(models.Order.quote_id == q['jti']).first()
    if existing:
        return existing  # Retry of the same checkout cannot reserve stock twice.
    if not product.is_active or order_in.quantity > product.quantity:
        raise HTTPException(409, 'Product is unavailable or has insufficient stock')
    product.quantity -= order_in.quantity
    order = models.Order(buyer_id=user.id, product_id=product.id, quantity=order_in.quantity,
        total_price=Decimal(q['product_cost']), status='pending', delivery_location=destination,
        expires_at=models.utcnow() + timedelta(hours=RESERVATION_HOURS), quote_id=q['jti'],
        product_name=product.name, unit='kg', unit_price=product.price_per_unit,
        pickup_location=product.location, transport_cost=Decimal(q['transport_cost']),
        grand_total=Decimal(q['estimated_total']), distance_km=Decimal(q['distance_km']),
        vehicle_type=q['vehicle_type'], vehicle_rate=Decimal(q['vehicle_rate_per_km']),
        pickup_latitude=Decimal(str(q['pickup']['latitude'])),
        pickup_longitude=Decimal(str(q['pickup']['longitude'])),
        delivery_latitude=Decimal(str(q['delivery']['latitude'])),
        delivery_longitude=Decimal(str(q['delivery']['longitude'])))
    db.add(order)
    commit(db)
    return order

@router.get('/my', response_model=list[schemas.OrderOut])
def get_my_orders(db: Session = Depends(get_db), user: models.User = Depends(auth.require_buyer),
                  offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    return (db.query(models.Order).filter(models.Order.buyer_id == user.id)
            .order_by(models.Order.id.desc()).offset(offset).limit(limit).all())

@router.get('/farmer', response_model=list[schemas.OrderOut])
def get_farmer_orders(db: Session = Depends(get_db), user: models.User = Depends(auth.require_farmer),
                      offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    return (db.query(models.Order).join(models.Product).filter(models.Product.farmer_id == user.id)
            .order_by(models.Order.id.desc()).offset(offset).limit(limit).all())

@router.put('/{order_id}/status', response_model=schemas.OrderOut)
def update_order_status(order_id: int, status_update: schemas.OrderStatusUpdate,
                        db: Session = Depends(get_db), user: models.User = Depends(auth.require_farmer)):
    order = get_or_404(db, models.Order, order_id, lock=True)
    product = get_or_404(db, models.Product, order.product_id, lock=True)
    if product.farmer_id != user.id:
        raise HTTPException(403, 'You can only manage orders for your products')
    if order.status != 'pending':
        raise HTTPException(409, 'Only pending orders can be accepted or rejected')
    if expired(order):
        release_stock(db, order, 'expired')
        commit(db)
        raise HTTPException(409, 'Reservation expired; stock has been released')
    if status_update.status == 'rejected':
        release_stock(db, order, 'rejected')
    else:
        if order.transport_cost is None or not order.pickup_location or not order.delivery_location:
            raise HTTPException(409, 'Legacy order has no agreed delivery quote; reject and ask buyer to reorder')
        order.status = 'accepted'
        db.add(models.Delivery(order_id=order.id, pickup_location=order.pickup_location,
            delivery_location=order.delivery_location, transport_cost=order.transport_cost, status='available'))
    commit(db)
    return order

@router.post('/{order_id}/cancel', response_model=schemas.OrderOut)
def cancel_order(order_id: int, db: Session = Depends(get_db),
                 user: models.User = Depends(auth.require_buyer)):
    order = get_or_404(db, models.Order, order_id, lock=True)
    if order.buyer_id != user.id:
        raise HTTPException(403, 'You can only cancel your own orders')
    if order.status in {'cancelled','expired'}:
        return order
    release_stock(db, order, 'expired' if expired(order) else 'cancelled')
    commit(db)
    return order

@router.get('/{order_id}', response_model=schemas.OrderOut)
def get_order(order_id: int, db: Session = Depends(get_db),
              user: models.User = Depends(auth.get_current_user)):
    order = get_or_404(db, models.Order, order_id)
    allowed = user.role == 'buyer' and order.buyer_id == user.id
    if user.role == 'farmer':
        allowed = order.product.farmer_id == user.id
    if not allowed:
        raise HTTPException(403, 'You cannot view this order')
    return order
