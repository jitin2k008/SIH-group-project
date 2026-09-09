"""CHANGED: transitions are atomic. Lock order: Delivery -> Order -> Product -> Transporter."""
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload
import auth, models, schemas
from database import get_db
from services.common import get_or_404, commit
from services.pricing import make_quote

router = APIRouter(prefix='/deliveries', tags=['Deliveries'])
TRANSITIONS = {'assigned':{'picked_up','failed'}, 'picked_up':{'in_transit','failed'},
               'in_transit':{'delivered','failed'}}

def build_delivery_response(delivery):
    order = delivery.order
    return {'id':delivery.id, 'order_id':order.id, 'transporter_id':delivery.transporter_id,
        'product_name':order.product_name or order.product.name, 'quantity':order.quantity,
        'unit':order.unit or order.product.unit, 'pickup_location':delivery.pickup_location,
        'delivery_location':delivery.delivery_location, 'transport_cost':delivery.transport_cost,
        'status':delivery.status}

def transporter_profile(db, user_id):
    row = (db.query(models.Transporter).filter(models.Transporter.user_id == user_id)
           .populate_existing().with_for_update().first())
    if row is None:
        raise HTTPException(409, 'Transporter profile is missing')
    return row

def free_transporter(db, user_id, finished_delivery_id):
    transporter = transporter_profile(db, user_id)
    # Also handles legacy users who were assigned multiple jobs by the original backend.
    another = db.query(models.Delivery.id).filter(models.Delivery.transporter_id == user_id,
        models.Delivery.id != finished_delivery_id,
        models.Delivery.status.in_(['assigned','picked_up','in_transit','failed'])).first()
    transporter.is_available = 'busy' if another else 'available'

@router.get('/estimate')
def get_delivery_estimate(product_id: int, quantity: Decimal = Query(..., gt=0, le=20000, decimal_places=3),
                          destination: str = Query(..., min_length=1, max_length=250),
                          db: Session = Depends(get_db), user: models.User = Depends(auth.require_buyer)):
    if not quantity.is_finite():
        raise HTTPException(422, 'Quantity must be finite')
    product = get_or_404(db, models.Product, product_id)
    return make_quote(product, quantity, destination.strip(), user.id)

def delivery_list(db, condition, offset, limit):
    rows = (db.query(models.Delivery).filter(condition)
        .options(selectinload(models.Delivery.order).selectinload(models.Order.product))
        .order_by(models.Delivery.id.desc()).offset(offset).limit(limit).all())
    return [build_delivery_response(d) for d in rows]

@router.get('/available', response_model=list[schemas.DeliveryOut])
def get_available_deliveries(db: Session = Depends(get_db), user: models.User = Depends(auth.require_transporter),
                            offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    return delivery_list(db, models.Delivery.status == 'available', offset, limit)

@router.get('/my', response_model=list[schemas.DeliveryOut])
def get_my_deliveries(db: Session = Depends(get_db), user: models.User = Depends(auth.require_transporter),
                      offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
    return delivery_list(db, models.Delivery.transporter_id == user.id, offset, limit)

@router.post('/{delivery_id}/accept', response_model=schemas.DeliveryOut)
def accept_delivery(delivery_id: int, db: Session = Depends(get_db),
                    user: models.User = Depends(auth.require_transporter)):
    delivery = get_or_404(db, models.Delivery, delivery_id, lock=True)
    if delivery.status != 'available':
        raise HTTPException(409, 'This delivery is no longer available')
    order = get_or_404(db, models.Order, delivery.order_id, lock=True)
    if order.status != 'accepted':
        raise HTTPException(409, 'Order is not ready for delivery')
    unit = order.unit or order.product.unit
    if unit.lower() not in {'kg','kgs','kilogram','kilograms'}:
        raise HTTPException(409, 'Legacy delivery weight is not in kilograms; resolve before assignment')
    transporter = transporter_profile(db, user.id)
    active = db.query(models.Delivery.id).filter(models.Delivery.transporter_id == user.id,
        models.Delivery.status.in_(['assigned','picked_up','in_transit','failed'])).first()
    if transporter.is_available != 'available' or active:
        raise HTTPException(409, 'Complete or return your current delivery before accepting another')
    if transporter.capacity_kg < order.quantity:
        raise HTTPException(409, 'Vehicle capacity is insufficient')
    delivery.transporter_id = user.id
    delivery.status = 'assigned'
    transporter.is_available = 'busy'
    commit(db)
    return build_delivery_response(delivery)

@router.put('/{delivery_id}/status', response_model=schemas.DeliveryOut)
def update_delivery_status(delivery_id: int, status_update: schemas.DeliveryStatusUpdate,
                           db: Session = Depends(get_db), user: models.User = Depends(auth.require_transporter)):
    delivery = get_or_404(db, models.Delivery, delivery_id, lock=True)
    if delivery.transporter_id != user.id:
        raise HTTPException(403, 'You can only manage your own deliveries')
    if status_update.status not in TRANSITIONS.get(delivery.status, set()):
        raise HTTPException(409, f'Cannot change {delivery.status} to {status_update.status}')
    order = get_or_404(db, models.Order, delivery.order_id, lock=True)
    delivery.status = status_update.status
    if delivery.status == 'delivered':
        order.status = 'completed'
        free_transporter(db, user.id, delivery.id)
    elif delivery.status == 'failed':
        order.status = 'delivery_failed'
        # Goods may still be with the driver: keep stock reserved and transporter busy.
    commit(db)
    return build_delivery_response(delivery)

@router.post('/{delivery_id}/confirm-return', response_model=schemas.DeliveryOut)
def confirm_goods_return(delivery_id: int, db: Session = Depends(get_db),
                         user: models.User = Depends(auth.require_farmer)):
    delivery = get_or_404(db, models.Delivery, delivery_id, lock=True)
    order = get_or_404(db, models.Order, delivery.order_id, lock=True)
    product = get_or_404(db, models.Product, order.product_id, lock=True)
    if product.farmer_id != user.id:
        raise HTTPException(403, 'You can only confirm returns for your products')
    if delivery.status == 'returned':
        return build_delivery_response(delivery)  # Idempotent: stock is not added again.
    if delivery.status != 'failed' or order.status != 'delivery_failed':
        raise HTTPException(409, 'Only failed deliveries can be returned')
    product.quantity += order.quantity
    delivery.status = 'returned'
    order.status = 'returned'
    if delivery.transporter_id is not None:
        free_transporter(db, delivery.transporter_id, delivery.id)
    commit(db)
    return build_delivery_response(delivery)

@router.get('/{delivery_id}', response_model=schemas.DeliveryOut)
def get_delivery(delivery_id: int, db: Session = Depends(get_db),
                 user: models.User = Depends(auth.get_current_user)):
    delivery = get_or_404(db, models.Delivery, delivery_id)
    order = delivery.order
    allowed = ((user.role == 'transporter' and delivery.transporter_id == user.id)
        or (user.role == 'buyer' and order.buyer_id == user.id)
        or (user.role == 'farmer' and order.product.farmer_id == user.id))
    if not allowed:
        raise HTTPException(403, 'You cannot view this delivery')
    return build_delivery_response(delivery)
