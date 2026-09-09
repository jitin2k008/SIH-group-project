from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import auth, models, schemas
from database import get_db
from services.common import get_or_404, commit

router = APIRouter(prefix='/products', tags=['Products'])

@router.post('/', response_model=schemas.ProductOut, status_code=201)
def create_product(product_in: schemas.ProductCreate, db: Session = Depends(get_db),
                   user: models.User = Depends(auth.require_farmer)):
    data = product_in.model_dump()
    data['location'] = data['location'] or (user.farmer_profile.location if user.farmer_profile else None) or user.location
    if not data['location'] or data['location'].strip().lower() == 'unknown':
        raise HTTPException(422, 'A pickup location is required')
    product = models.Product(**data, farmer_id=user.id)
    db.add(product)
    commit(db)
    return product

@router.get('/', response_model=list[schemas.ProductOut])
def get_products(name: str | None = Query(None, max_length=250),
                 location: str | None = Query(None, max_length=250),
                 min_price: Decimal | None = Query(None, ge=0, le=100000000),
                 max_price: Decimal | None = Query(None, ge=0, le=100000000),
                 offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                 db: Session = Depends(get_db)):
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(422, 'min_price cannot exceed max_price')
    query = db.query(models.Product).filter(models.Product.is_active.is_(True))
    if name:
        query = query.filter(models.Product.name.ilike(f'%{name}%'))
    if location:
        query = query.filter(models.Product.location.ilike(f'%{location}%'))
    if min_price is not None:
        query = query.filter(models.Product.price_per_unit >= min_price)
    if max_price is not None:
        query = query.filter(models.Product.price_per_unit <= max_price)
    return query.order_by(models.Product.id).offset(offset).limit(limit).all()

def owned_product(db, product_id, user):
    product = get_or_404(db, models.Product, product_id, lock=True)
    if product.farmer_id != user.id:
        raise HTTPException(403, 'You can only modify your own listings')
    if not product.is_active:
        raise HTTPException(409, 'Listing is archived')
    return product

@router.patch('/{product_id}', response_model=schemas.ProductOut)
def update_product(product_id: int, product_in: schemas.ProductUpdate,
                   db: Session = Depends(get_db), user: models.User = Depends(auth.require_farmer)):
    product = owned_product(db, product_id, user)
    data = product_in.model_dump(exclude_unset=True)
    if 'unit' in data and data['unit'] != product.unit:
        if db.query(models.Order.id).filter(models.Order.product_id == product.id,
                models.Order.status.in_(['pending','accepted','delivery_failed'])).first():
            raise HTTPException(409, 'Cannot change units while orders are active')
        if 'quantity' not in data or 'price_per_unit' not in data:
            raise HTTPException(422, 'Unit conversion requires converted quantity and price_per_unit')
    if 'quantity' in data and db.query(models.Order.id).filter(models.Order.product_id == product.id,
            models.Order.status.in_(['pending','accepted','delivery_failed'])).first():
        raise HTTPException(409, 'Active orders exist; use /stock-adjustment to adjust available stock')
    for field, value in data.items():
        setattr(product, field, value)
    commit(db)
    return product

@router.post('/{product_id}/stock-adjustment', response_model=schemas.ProductOut)
def adjust_stock(product_id: int, data: schemas.StockAdjustment,
                 db: Session = Depends(get_db), user: models.User = Depends(auth.require_farmer)):
    product = owned_product(db, product_id, user)
    quantity = product.quantity + data.delta
    if not 0 <= quantity <= 1000000:
        raise HTTPException(409, 'Resulting available stock must be between 0 and 1000000 kg')
    product.quantity = quantity
    commit(db)
    return product

@router.delete('/{product_id}')
def delete_product(product_id: int, db: Session = Depends(get_db),
                   user: models.User = Depends(auth.require_farmer)):
    product = owned_product(db, product_id, user)
    product.is_active = False  # CHANGED: preserve references and order history.
    commit(db)
    return {'message':'Product archived; existing orders remain available'}

@router.get('/{product_id}', response_model=schemas.ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = get_or_404(db, models.Product, product_id)
    if not product.is_active:
        raise HTTPException(404, 'Product not found')
    return product
