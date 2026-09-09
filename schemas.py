"""CHANGED: validate at the API boundary; keep separate status contracts."""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=250)]
Weight = Annotated[Decimal, Field(gt=0, le=1000000, max_digits=14, decimal_places=3)]
Stock = Annotated[Decimal, Field(ge=0, le=1000000, max_digits=14, decimal_places=3)]
Price = Annotated[Decimal, Field(gt=0, le=100000000, max_digits=16, decimal_places=2)]
CoordinatesLatitude = Annotated[Decimal, Field(ge=-90, le=90, decimal_places=7)]
CoordinatesLongitude = Annotated[Decimal, Field(ge=-180, le=180, decimal_places=7)]

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)

class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)

class BaseUserRegister(Input):
    name: Text
    email: EmailStr
    phone: Text | None = None
    password: Annotated[str, Field(min_length=8, max_length=72)]
    location: Text | None = None

    @field_validator('password')
    @classmethod
    def bcrypt_limit(cls, value):
        if len(value.encode('utf-8')) > 72:
            raise ValueError('Password must be at most 72 UTF-8 bytes')
        return value

class FarmerRegister(BaseUserRegister):
    farm_name: Text | None = None
    farm_location: Text | None = None

class BuyerRegister(BaseUserRegister):
    pass

class TransporterRegister(BaseUserRegister):
    vehicle_type: Text
    vehicle_number: Text
    capacity_kg: Weight

    @field_validator('vehicle_number')
    @classmethod
    def normalize_vehicle(cls, value):
        return value.upper().replace(' ', '').replace('-', '')

class UserOut(Output):
    id: int
    name: str
    email: str
    role: str
    location: str | None = None

class Token(Output):
    access_token: str
    token_type: str = 'bearer'

class ProductCreate(Input):
    name: Text
    description: Annotated[str, Field(max_length=5000)] | None = None
    quantity: Stock
    unit: Text
    price_per_unit: Price
    location: Text | None = None

    @field_validator('unit')
    @classmethod
    def kilograms(cls, value):
        if value.lower() not in {'kg','kgs','kilogram','kilograms'}:
            raise ValueError('This prototype supports kilograms only; use kg')
        return 'kg'

class ProductUpdate(Input):
    name: Text | None = None
    description: Annotated[str, Field(max_length=5000)] | None = None
    quantity: Stock | None = None
    unit: Text | None = None
    price_per_unit: Price | None = None
    location: Text | None = None

    @field_validator('name', 'quantity', 'unit', 'price_per_unit', 'location')
    @classmethod
    def not_null(cls, value):
        if value is None:
            raise ValueError('Omit this field instead of sending null')
        return value

    @field_validator('unit')
    @classmethod
    def kilograms(cls, value):
        return ProductCreate.kilograms(value)

class StockAdjustment(Input):
    delta: Annotated[Decimal, Field(ge=-1000000, le=1000000, decimal_places=3)]

class ProductOut(Output):
    id: int
    farmer_id: int
    name: str
    description: str | None
    quantity: Decimal
    unit: str
    price_per_unit: Decimal
    location: str | None
    is_active: bool

class OrderCreate(Input):
    product_id: Annotated[int, Field(gt=0)]
    quantity: Weight
    delivery_location: Text | None = None
    # Use the /deliveries/estimate quote to confirm the displayed price and coordinates.
    quote_token: str

class OrderOut(Output):
    id: int
    buyer_id: int
    product_id: int
    quantity: Decimal
    total_price: Decimal
    status: str
    delivery_location: str | None
    created_at: datetime
    expires_at: datetime | None
    product_name: str | None
    unit: str | None
    unit_price: Decimal | None
    pickup_location: str | None
    transport_cost: Decimal | None
    grand_total: Decimal | None
    distance_km: Decimal | None
    vehicle_type: str | None

class OrderStatusUpdate(Input):
    status: Literal['accepted', 'rejected']

class DeliveryStatusUpdate(Input):
    status: Literal['picked_up', 'in_transit', 'delivered', 'failed']

class DeliveryOut(Output):
    id: int
    order_id: int
    transporter_id: int | None
    product_name: str
    quantity: Decimal
    unit: str
    pickup_location: str
    delivery_location: str
    transport_cost: Decimal
    status: str
