"""Run with pytest after installing requirements-dev.txt. Uses isolated SQLite and mocked maps.
These tests do not prove PostgreSQL row-lock behavior; see test_postgres.py.
"""
import os
os.environ['DATABASE_URL'] = 'sqlite://'
os.environ['SECRET_KEY'] = 'test-only-secret-with-at-least-32-bytes-1234'
from datetime import timedelta
from decimal import Decimal
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import models
from database import Base, get_db
from main import app
from services import pricing

@pytest.fixture
def setup(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, record):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    def db_override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = db_override
    monkeypatch.setattr(pricing, 'get_route_details', lambda a,b: {
        'distance_km':10, 'pickup':{'latitude':28.6,'longitude':77.2},
        'destination':{'latitude':28.7,'longitude':77.3}})
    with TestClient(app) as client:
        yield client, factory
    app.dependency_overrides.clear()
    engine.dispose()

def register(client, role, number=1, **extra):
    data = {'name':f'{role}{number}', 'email':f'{role}{number}@example.com',
            'password':'password123', 'location':'Delhi', **extra}
    if role == 'transporter':
        data = {**data,'vehicle_type':'Mini Truck','vehicle_number':f'DL01AB{number:04}',
                'capacity_kg':extra.get('capacity_kg',500)}
    r = client.post(f'/auth/register/{role}', json=data)
    assert r.status_code == 201, r.text
    r = client.post('/auth/login',data={'username':data['email'],'password':data['password']})
    assert r.status_code == 200, r.text
    return {'Authorization':'Bearer '+r.json()['access_token']}

def listing(client, farmer):
    r = client.post('/products/',headers=farmer,json={'name':'Wheat','quantity':'100',
        'unit':'kg','price_per_unit':'20','location':'Delhi'})
    assert r.status_code == 201, r.text
    return r.json()['id']

def order(client,buyer,product_id,quantity='10'):
    q = client.get('/deliveries/estimate', headers=buyer,params={'product_id':product_id,
        'quantity':quantity,'destination':'Noida'})
    assert q.status_code == 200, q.text
    body = {'product_id':product_id,'quantity':quantity,'delivery_location':'Noida',
            'quote_token':q.json()['quote_token']}
    r = client.post('/orders/',headers=buyer,json=body)
    assert r.status_code == 201,r.text
    return r.json(),body

def accepted_delivery(client,factory,farmer,buyer,pid):
    o,_ = order(client,buyer,pid)
    r = client.put(f"/orders/{o['id']}/status",headers=farmer,json={'status':'accepted'})
    assert r.status_code == 200, r.text
    with factory() as db:
        return db.query(models.Delivery).filter_by(order_id=o['id']).one().id

def test_quote_stock_retry_and_cancel(setup):
    client,factory=setup
    farmer=register(client,'farmer'); buyer=register(client,'buyer')
    pid=listing(client,farmer)
    o,body=order(client,buyer,pid)
    assert Decimal(o['total_price']) == 200
    assert Decimal(o['transport_cost']) == 100
    assert Decimal(o['grand_total']) == 300
    retry=client.post('/orders/',headers=buyer,json=body)
    assert retry.json()['id'] == o['id']
    assert Decimal(client.get(f'/products/{pid}').json()['quantity']) == 90
    for _ in range(2):
        assert client.post(f"/orders/{o['id']}/cancel",headers=buyer).status_code == 200
    assert Decimal(client.get(f'/products/{pid}').json()['quantity']) == 100

def test_delivery_busy_return_and_history(setup):
    client,factory=setup
    farmer=register(client,'farmer'); buyer=register(client,'buyer')
    driver=register(client,'transporter'); other=register(client,'transporter',2)
    pid=listing(client,farmer)
    did=accepted_delivery(client,factory,farmer,buyer,pid)
    did2=accepted_delivery(client,factory,farmer,buyer,pid)
    assert client.post(f'/deliveries/{did}/accept',headers=driver).status_code == 200
    assert client.post(f'/deliveries/{did}/accept',headers=other).status_code == 409
    assert client.post(f'/deliveries/{did2}/accept',headers=driver).status_code == 409
    assert client.put(f'/deliveries/{did}/status',headers=driver,json={'status':'delivered'}).status_code == 409
    assert client.put(f'/deliveries/{did}/status',headers=driver,json={'status':'failed'}).status_code == 200
    assert Decimal(client.get(f'/products/{pid}').json()['quantity']) == 80
    for _ in range(2):
        assert client.post(f'/deliveries/{did}/confirm-return',headers=farmer).status_code == 200
    assert Decimal(client.get(f'/products/{pid}').json()['quantity']) == 90
    assert client.post(f'/deliveries/{did2}/accept',headers=driver).status_code == 200
    assert client.patch(f'/products/{pid}',headers=farmer,json={'name':'New name'}).status_code == 200
    assert client.get(f'/deliveries/{did2}',headers=buyer).json()['product_name'] == 'Wheat'
    for status in ['picked_up','in_transit','delivered']:
        assert client.put(f'/deliveries/{did2}/status',headers=driver,json={'status':status}).status_code == 200
    assert client.delete(f'/products/{pid}',headers=farmer).status_code == 200
    assert client.get(f'/products/{pid}').status_code == 404
    assert client.get(f'/deliveries/{did2}',headers=buyer).status_code == 200

def test_validation_permissions_and_expiry(setup):
    client,factory=setup
    farmer=register(client,'farmer'); buyer=register(client,'buyer'); stranger=register(client,'buyer',2)
    pid=listing(client,farmer)
    for payload in [{'quantity':-1},{'quantity':None},{'price_per_unit':'NaN'},{'name':'   '},{'unit':'bags'}]:
        assert client.patch(f'/products/{pid}',headers=farmer,json=payload).status_code == 422
    assert client.delete(f'/products/{pid}',headers=buyer).status_code == 403
    o,body=order(client,buyer,pid)
    assert client.get(f"/orders/{o['id']}",headers=stranger).status_code == 403
    with factory() as db:
        db.get(models.Order,o['id']).expires_at=models.utcnow()-timedelta(seconds=1)
        db.commit()
    assert client.put(f"/orders/{o['id']}/status",headers=farmer,json={'status':'accepted'}).status_code == 409
    assert Decimal(client.get(f'/products/{pid}').json()['quantity']) == 100

def test_registration_atomicity_and_invalid_token(setup):
    from jose import jwt
    from config import SECRET_KEY
    client,factory=setup
    register(client,'transporter')
    r=client.post('/auth/register/transporter',json={'name':'duplicate','email':'new@example.com',
        'password':'password123','vehicle_type':'Mini Truck','vehicle_number':'DL01AB0001','capacity_kg':500})
    assert r.status_code == 409
    with factory() as db:
        assert db.query(models.User).filter_by(email='new@example.com').first() is None
    token=jwt.encode({'sub':'not-an-integer','type':'access','exp':models.utcnow()+timedelta(hours=1)},SECRET_KEY,algorithm='HS256')
    assert client.get('/auth/me',headers={'Authorization':'Bearer '+token}).status_code == 401

def test_changed_quote_and_insufficient_capacity(setup):
    client,factory=setup
    farmer=register(client,'farmer'); buyer=register(client,'buyer')
    driver=register(client,'transporter',capacity_kg=5)
    pid=listing(client,farmer)
    q=client.get('/deliveries/estimate',headers=buyer,params={'product_id':pid,'quantity':10,'destination':'Noida'}).json()
    client.patch(f'/products/{pid}',headers=farmer,json={'price_per_unit':'21'})
    assert client.post('/orders/',headers=buyer,json={'product_id':pid,'quantity':10,
        'delivery_location':'Noida','quote_token':q['quote_token']}).status_code == 409
    did=accepted_delivery(client,factory,farmer,buyer,pid)
    assert client.post(f'/deliveries/{did}/accept',headers=driver).status_code == 409
