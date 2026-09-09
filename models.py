"""CHANGED: decimal amounts, UTC dates, immutable order details and constraints."""
from datetime import datetime, timezone
from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship
from database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = 'users'
    __table_args__ = (CheckConstraint("role IN ('farmer','buyer','transporter')", name='ck_user_role'),)
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)
    location = Column(String)
    farmer_profile = relationship('Farmer', back_populates='user', uselist=False)


class Farmer(Base):
    __tablename__ = 'farmers'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True, nullable=False)
    farm_name = Column(String)
    # Farm address; User.location is the person's contact address. Legacy data is preserved.
    location = Column(String)
    user = relationship('User', back_populates='farmer_profile')


class Product(Base):
    __tablename__ = 'products'
    __table_args__ = (
        CheckConstraint('quantity >= 0 AND quantity <= 1000000', name='ck_product_quantity'),
        CheckConstraint('price_per_unit > 0 AND price_per_unit <= 100000000', name='ck_product_price'),
    )
    id = Column(Integer, primary_key=True)
    farmer_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    name = Column(String, nullable=False)
    description = Column(String)
    quantity = Column(Numeric(14, 3), nullable=False)  # Available stock, excluding reservations.
    unit = Column(String, nullable=False)
    price_per_unit = Column(Numeric(16, 2), nullable=False)
    location = Column(String)
    is_active = Column(Boolean, nullable=False, default=True)
    farmer = relationship('User')


class Order(Base):
    __tablename__ = 'orders'
    __table_args__ = (
        CheckConstraint('quantity > 0 AND quantity <= 1000000', name='ck_order_quantity'),
        CheckConstraint('total_price >= 0 AND total_price <= 100000000000000', name='ck_order_price'),
        CheckConstraint("status IN ('pending','accepted','rejected','completed','delivery_failed','returned','cancelled','expired')", name='ck_order_status'),
    )
    id = Column(Integer, primary_key=True)
    buyer_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey('products.id'), nullable=False, index=True)
    quantity = Column(Numeric(14, 3), nullable=False)
    total_price = Column(Numeric(18, 2), nullable=False)  # Product subtotal, kept for API compatibility.
    status = Column(String, nullable=False, default='pending', index=True)
    delivery_location = Column(String)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    expires_at = Column(DateTime(timezone=True), index=True)
    quote_id = Column(String, unique=True)
    # Nullable for legacy orders whose original details cannot be reconstructed exactly.
    product_name = Column(String)
    unit = Column(String)
    unit_price = Column(Numeric(16, 2))
    pickup_location = Column(String)
    transport_cost = Column(Numeric(16, 2))
    grand_total = Column(Numeric(18, 2))
    distance_km = Column(Numeric(12, 2))
    vehicle_type = Column(String)
    vehicle_rate = Column(Numeric(10, 2))
    pickup_latitude = Column(Numeric(10, 7))
    pickup_longitude = Column(Numeric(10, 7))
    delivery_latitude = Column(Numeric(10, 7))
    delivery_longitude = Column(Numeric(10, 7))
    buyer = relationship('User')
    product = relationship('Product')


class Transporter(Base):
    __tablename__ = 'transporters'
    __table_args__ = (
        CheckConstraint('capacity_kg > 0 AND capacity_kg <= 1000000', name='ck_transporter_capacity'),
        CheckConstraint("is_available IN ('available','busy')", name='ck_transporter_availability'),
    )
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True, nullable=False)
    vehicle_type = Column(String, nullable=False)
    vehicle_number = Column(String, nullable=False, unique=True)
    capacity_kg = Column(Numeric(14, 3), nullable=False)
    is_available = Column(String, nullable=False, default='available')
    user = relationship('User')


class Delivery(Base):
    __tablename__ = 'deliveries'
    __table_args__ = (
        CheckConstraint('transport_cost >= 0 AND transport_cost <= 100000000000000', name='ck_delivery_cost'),
        CheckConstraint("status IN ('available','assigned','picked_up','in_transit','delivered','failed','returned')", name='ck_delivery_status'),
    )
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id'), unique=True, nullable=False)
    transporter_id = Column(Integer, ForeignKey('users.id'), index=True)
    pickup_location = Column(String, nullable=False)
    delivery_location = Column(String, nullable=False)
    transport_cost = Column(Numeric(18, 2), nullable=False)
    status = Column(String, nullable=False, default='available', index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utcnow)
    order = relationship('Order')
    transporter = relationship('User')
