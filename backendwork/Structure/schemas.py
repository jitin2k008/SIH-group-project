from typing import Optional

from pydantic import BaseModel, EmailStr


# ==================================================
# USER REGISTRATION SCHEMAS
# ==================================================

class BaseUserRegister(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None
    password: str
    location: Optional[str] = None


class FarmerRegister(BaseUserRegister):
    farm_name: Optional[str] = None


class BuyerRegister(BaseUserRegister):
    pass


class TransporterRegister(BaseUserRegister):
    vehicle_type: str
    vehicle_number: str
    capacity_kg: float


# ==================================================
# LOGIN
# ==================================================

class UserLogin(BaseModel):
    email: EmailStr
    password: str


# ==================================================
# USER RESPONSE
# ==================================================

class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    location: Optional[str] = None

    class Config:
        orm_mode = True


# ==================================================
# TOKEN
# ==================================================

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ==================================================
# PRODUCT
# ==================================================

class ProductCreate(BaseModel):
    name: str
    description: Optional[str] = None
    quantity: float
    unit: str
    price_per_unit: float
    location: Optional[str] = None


class ProductOut(BaseModel):
    id: int
    farmer_id: int
    name: str
    description: Optional[str] = None
    quantity: float
    unit: str
    price_per_unit: float
    location: Optional[str] = None

    class Config:
        orm_mode = True


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    price_per_unit: Optional[float] = None
    location: Optional[str] = None


# ==================================================
# TRANSPORTER RESPONSE
# ==================================================

class TransporterOut(BaseModel):
    id: int
    user_id: int
    vehicle_type: str
    vehicle_number: str
    capacity_kg: float
    is_available: str

    class Config:
        orm_mode = True


# ==================================================
# DELIVERY RESPONSE
# ==================================================

class DeliveryOut(BaseModel):
    id: int
    order_id: int

    product_name: str
    quantity: float
    unit: str

    pickup_location: str
    delivery_location: str
    transport_cost: float
    status: str

    class Config:
        orm_mode = True


# ==================================================
# ORDER
# ==================================================

class OrderCreate(BaseModel):
    product_id: int
    quantity: float
    delivery_location: Optional[str] = None


class OrderOut(BaseModel):
    id: int
    buyer_id: int
    product_id: int
    quantity: float
    total_price: float
    status: str
    delivery_location: Optional[str] = None
    created_at: str

    class Config:
        orm_mode = True


class OrderStatusUpdate(BaseModel):
    status: str