"""Run every minute using Task Scheduler/cron: python expire_orders.py."""
from database import SessionLocal
import models
from services.orders import expired, release_stock
from services.common import commit

def run():
    with SessionLocal() as db:
        ids = [row[0] for row in db.query(models.Order.id).filter(models.Order.status == 'pending',
            models.Order.expires_at <= models.utcnow()).order_by(models.Order.id).all()]
    count = 0
    for order_id in ids:
        with SessionLocal() as db:
            order = db.query(models.Order).filter(models.Order.id == order_id).with_for_update().first()
            if order and order.status == 'pending' and expired(order):
                release_stock(db, order, 'expired')
                commit(db)
                count += 1
    return count

if __name__ == '__main__':
    print(f'Expired {run()} pending reservations')
