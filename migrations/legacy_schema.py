"""Frozen original schema, used only to initialize/adopt the supplied legacy database."""
from sqlalchemy import Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.orm import declarative_base
Base = declarative_base()


# One table for everyone (farmer or buyer). The "role" column tells them apart.
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # "farmer" or "buyer"
    location = Column(String, nullable=True)

    # If this user is a farmer, this links to their extra profile info below.
    farmer_profile = relationship("Farmer", back_populates="user", uselist=False)


# Extra info that only farmers need (matches the FARMERS table in your DB design).
class Farmer(Base):
    __tablename__ = "farmers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    farm_name = Column(String, nullable=True)
    location = Column(String, nullable=True)
    rating = Column(Float, default=0.0)

    user = relationship("User", back_populates="farmer_profile")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)

    # The farmer who owns this listing
    farmer_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    name = Column(String, nullable=False)
    description = Column(String, nullable=True)

    quantity = Column(Float, nullable=False)
    unit = Column(String, nullable=False)

    price_per_unit = Column(Float, nullable=False)

    location = Column(String, nullable=True)

    farmer = relationship("User")


from datetime import datetime

# --------------------------------------------------
# ORDER
# Connects a buyer with a farmer's product.
# --------------------------------------------------
class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)

    # Who placed the order
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Which product was ordered
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)

    # How much the buyer wants
    quantity = Column(Float, nullable=False)

    # Price at the time the order was placed
    total_price = Column(Float, nullable=False)

    # pending / accepted / rejected / completed
    status = Column(String, nullable=False, default="pending")

    # Where the buyer wants the product delivered
    delivery_location = Column(String, nullable=True)

    created_at = Column(
        String,
        default=lambda: datetime.utcnow().isoformat()
    )

    buyer = relationship("User")
    product = relationship("Product")


from datetime import datetime


# --------------------------------------------------
# TRANSPORTER
# Extra profile information for users whose role
# is "transporter".
# --------------------------------------------------
class Transporter(Base):
    __tablename__ = "transporters"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        unique=True,
        nullable=False
    )

    vehicle_type = Column(String, nullable=False)
    vehicle_number = Column(String, nullable=False, unique=True)

    # Maximum weight the vehicle can carry.
    capacity_kg = Column(Float, nullable=False)

    # True = transporter is currently available
    is_available = Column(
        String,
        nullable=False,
        default="available"
    )

    user = relationship("User")


# --------------------------------------------------
# DELIVERY
# Created when a farmer accepts an order.
# --------------------------------------------------
class Delivery(Base):
    __tablename__ = "deliveries"

    id = Column(Integer, primary_key=True, index=True)

    # The order being transported
    order_id = Column(
        Integer,
        ForeignKey("orders.id"),
        unique=True,
        nullable=False
    )

    # Transporter who accepts the delivery.
    # NULL until someone accepts it.
    transporter_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True
    )

    pickup_location = Column(String, nullable=False)
    delivery_location = Column(String, nullable=False)

    transport_cost = Column(Float, nullable=False)

    # available / assigned / picked_up / in_transit / delivered
    status = Column(
        String,
        nullable=False,
        default="available"
    )

    created_at = Column(
        String,
        default=lambda: datetime.utcnow().isoformat()
    )

    order = relationship("Order")
    transporter = relationship("User")