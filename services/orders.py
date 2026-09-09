"""Stock-changing actions lock Order, then Product, in this order."""
from datetime import timezone
from fastapi import HTTPException
import models
from services.common import get_or_404


def expired(order):
    expires = order.expires_at
    if expires is None:
        return False
    if expires.tzinfo is None:  # SQLite tests; PostgreSQL returns aware values.
        expires = expires.replace(tzinfo=timezone.utc)
    return expires <= models.utcnow()


def release_stock(db, order, status):
    if order.status != 'pending':
        raise HTTPException(409, 'Only pending orders can release a reservation')
    product = get_or_404(db, models.Product, order.product_id, lock=True)
    product.quantity += order.quantity
    order.status = status

