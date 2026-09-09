"""Opt-in lock test. Creates/drops ONLY an isolated random schema in TEST_DATABASE_URL."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'), reason='Requires a dedicated PostgreSQL test database')
def test_concurrent_assignment():
    import models
    from database import Base
    from routers.delivery_routes import accept_delivery, update_delivery_status, confirm_goods_return
    import schemas
    from fastapi import HTTPException
    engine=create_engine(os.environ['TEST_DATABASE_URL'])
    schema='farmdirect_test_'+uuid.uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped=engine.execution_options(schema_translate_map={None:schema})
    factory=sessionmaker(bind=scoped,expire_on_commit=False,autoflush=False)
    try:
        Base.metadata.create_all(scoped)
        with factory() as db:
            users=[models.User(name=str(i),email=f'{i}@example.com',role=r,password_hash='unused')
                   for i,r in enumerate(['farmer','buyer','transporter','transporter'])]
            db.add_all(users); db.flush()
            p=models.Product(farmer_id=users[0].id,name='Wheat',quantity=90,unit='kg',price_per_unit=20)
            db.add(p); db.flush()
            o=models.Order(product_id=p.id,buyer_id=users[1].id,quantity=10,total_price=200,status='accepted',unit='kg',product_name='Wheat')
            db.add(o); db.flush()
            d=models.Delivery(order_id=o.id,pickup_location='Delhi',delivery_location='Noida',transport_cost=100)
            db.add(d)
            for i,u in enumerate(users[2:]):
                db.add(models.Transporter(user_id=u.id,vehicle_type='Truck',vehicle_number=str(i),capacity_kg=500))
            db.commit()
            did=d.id; pid=p.id; farmer_id=users[0].id; drivers=[u.id for u in users[2:]]
        barrier=Barrier(2)
        def attempt(uid):
            with factory() as db:
                try:
                    user=db.get(models.User,uid)
                    barrier.wait(timeout=10)
                    accept_delivery(did,db,user)
                    return 200
                except HTTPException as exc:
                    db.rollback()
                    return exc.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(attempt,drivers))
        assert sorted(results)==[200,409]
        with factory() as db:
            assert db.query(models.Transporter).filter_by(is_available='busy').count()==1
            winner=db.get(models.Delivery,did).transporter_id
            update_delivery_status(did, schemas.DeliveryStatusUpdate(status='failed'), db, db.get(models.User,winner))
        barrier=Barrier(2)
        def confirm(_):
            with factory() as db:
                farmer=db.get(models.User,farmer_id)
                barrier.wait(timeout=10)
                return confirm_goods_return(did,db,farmer)['status']
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert list(pool.map(confirm,range(2)))==['returned','returned']
        with factory() as db:
            assert db.get(models.Product,pid).quantity==100
            assert db.query(models.Transporter).filter_by(is_available='busy').count()==0
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()
