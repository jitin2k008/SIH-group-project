from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import auth
import models
import schemas
from database import get_db
from services.map_service import get_route_distance


router = APIRouter(
    prefix="/deliveries",
    tags=["Deliveries"]
)


# ==================================================
# VEHICLE RATE CONFIGURATION
# ==================================================
# Fixed prototype rates for SIH.
#
# These are charged per kilometer.
# ==================================================

VEHICLE_RATES = {
    "Small Pickup": 10.0,
    "Mini Truck": 15.0,
    "Medium Truck": 20.0,
    "Large Truck": 25.0
}


# ==================================================
# SELECT VEHICLE BASED ON QUANTITY
# ==================================================
def get_vehicle_for_quantity(quantity_kg: float):
    """
    Select the smallest suitable vehicle based on
    the quantity being transported.

    These limits are prototype values for SIH and
    can be adjusted later.
    """

    if quantity_kg <= 100:
        return "Small Pickup", VEHICLE_RATES["Small Pickup"]

    elif quantity_kg <= 500:
        return "Mini Truck", VEHICLE_RATES["Mini Truck"]

    elif quantity_kg <= 2000:
        return "Medium Truck", VEHICLE_RATES["Medium Truck"]

    else:
        return "Large Truck", VEHICLE_RATES["Large Truck"]


# ==================================================
# BUILD DELIVERY RESPONSE
# ==================================================
# Product information is obtained through:
#
# Delivery -> Order -> Product
#
# We do not duplicate product information inside
# the Delivery database table.
# ==================================================

def build_delivery_response(
    delivery: models.Delivery,
    db: Session
):

    # --------------------------------------------------
    # Find order
    # --------------------------------------------------
    order = (
        db.query(models.Order)
        .filter(
            models.Order.id == delivery.order_id
        )
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    # --------------------------------------------------
    # Find product
    # --------------------------------------------------
    product = (
        db.query(models.Product)
        .filter(
            models.Product.id == order.product_id
        )
        .first()
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    # --------------------------------------------------
    # Return complete delivery information
    # --------------------------------------------------
    return {
        "id": delivery.id,
        "order_id": delivery.order_id,

        "product_name": product.name,
        "quantity": order.quantity,
        "unit": product.unit,

        "pickup_location": delivery.pickup_location,
        "delivery_location": delivery.delivery_location,

        "transport_cost": delivery.transport_cost,
        "status": delivery.status
    }


# ==================================================
# GET DELIVERY ESTIMATE
# ==================================================
# Buyer can request an estimate BEFORE placing
# an order.
#
# This does NOT create an order.
#
# Input:
#   product_id
#   quantity
#   destination
#
# Output:
#   product cost
#   road distance
#   vehicle type
#   vehicle rate
#   transport cost
#   estimated total
# ==================================================

@router.get("/estimate")
def get_delivery_estimate(
    product_id: int,
    quantity: float,
    destination: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.get_current_user
    )
):

    # --------------------------------------------------
    # Only buyers can request an estimate
    # --------------------------------------------------
    if current_user.role != "buyer":
        raise HTTPException(
            status_code=403,
            detail="Only buyers can request delivery estimates"
        )

    # --------------------------------------------------
    # Validate quantity
    # --------------------------------------------------
    if quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail="Quantity must be greater than 0"
        )

    # --------------------------------------------------
    # Find product
    # --------------------------------------------------
    product = (
        db.query(models.Product)
        .filter(
            models.Product.id == product_id
        )
        .first()
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    # --------------------------------------------------
    # Check available stock
    # --------------------------------------------------
    if quantity > product.quantity:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Only {product.quantity} "
                f"{product.unit} available"
            )
        )

    # --------------------------------------------------
    # Current prototype works with kilograms
    # because transporter capacity is stored in kg.
    # --------------------------------------------------
    if product.unit.lower() not in (
        "kg",
        "kgs",
        "kilogram",
        "kilograms"
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Delivery estimation currently supports "
                "products listed in kilograms (kg)"
            )
        )

    # --------------------------------------------------
    # Product pickup location
    # --------------------------------------------------
    pickup_location = product.location

    if not pickup_location:
        raise HTTPException(
            status_code=400,
            detail="Product does not have a pickup location"
        )

    # --------------------------------------------------
    # Validate destination
    # --------------------------------------------------
    if not destination or not destination.strip():
        raise HTTPException(
            status_code=400,
            detail="Destination cannot be empty"
        )

    # --------------------------------------------------
    # Calculate road distance
    # --------------------------------------------------
    try:

        distance_km = get_route_distance(
            pickup_location,
            destination
        )

    except ValueError as e:

        raise HTTPException(
            status_code=404,
            detail=str(e)
        )

    except Exception:

        raise HTTPException(
            status_code=500,
            detail="Could not calculate road distance"
        )

    # --------------------------------------------------
    # Select suitable vehicle
    # --------------------------------------------------
    vehicle_type, vehicle_rate = (
        get_vehicle_for_quantity(quantity)
    )

    # --------------------------------------------------
    # Calculate product cost
    # --------------------------------------------------
    product_cost = (
        quantity *
        product.price_per_unit
    )

    # --------------------------------------------------
    # Calculate transport cost
    # --------------------------------------------------
    transport_cost = (
        distance_km *
        vehicle_rate
    )

    # --------------------------------------------------
    # Calculate estimated total
    # --------------------------------------------------
    estimated_total = (
        product_cost +
        transport_cost
    )

    # --------------------------------------------------
    # Return estimate
    # --------------------------------------------------
    return {
        "product_id": product.id,
        "product_name": product.name,

        "quantity": quantity,
        "unit": product.unit,

        "price_per_unit": product.price_per_unit,
        "product_cost": round(
            product_cost,
            2
        ),

        "pickup_location": pickup_location,
        "destination": destination,

        "distance_km": distance_km,

        "vehicle_type": vehicle_type,
        "vehicle_rate_per_km": vehicle_rate,

        "transport_cost": round(
            transport_cost,
            2
        ),

        "estimated_total": round(
            estimated_total,
            2
        )
    }


# ==================================================
# GET AVAILABLE DELIVERIES
# ==================================================
# Only transporters can see available delivery jobs.
# ==================================================

@router.get(
    "/available",
    response_model=list[schemas.DeliveryOut]
)
def get_available_deliveries(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.get_current_user
    )
):

    # --------------------------------------------------
    # Only transporters
    # --------------------------------------------------
    if current_user.role != "transporter":
        raise HTTPException(
            status_code=403,
            detail="Only transporters can view delivery jobs"
        )

    deliveries = (
        db.query(models.Delivery)
        .filter(
            models.Delivery.status == "available"
        )
        .all()
    )

    return [
        build_delivery_response(
            delivery,
            db
        )
        for delivery in deliveries
    ]


# ==================================================
# ACCEPT DELIVERY
# ==================================================
# Transporter accepts an available delivery.
# ==================================================

@router.post(
    "/{delivery_id}/accept",
    response_model=schemas.DeliveryOut
)
def accept_delivery(
    delivery_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.get_current_user
    )
):

    # --------------------------------------------------
    # Only transporters
    # --------------------------------------------------
    if current_user.role != "transporter":
        raise HTTPException(
            status_code=403,
            detail="Only transporters can accept deliveries"
        )

    # --------------------------------------------------
    # Find delivery
    # --------------------------------------------------
    delivery = (
        db.query(models.Delivery)
        .filter(
            models.Delivery.id == delivery_id
        )
        .first()
    )

    if not delivery:
        raise HTTPException(
            status_code=404,
            detail="Delivery not found"
        )

    # --------------------------------------------------
    # Must still be available
    # --------------------------------------------------
    if delivery.status != "available":
        raise HTTPException(
            status_code=400,
            detail="This delivery is no longer available"
        )

    # --------------------------------------------------
    # Find transporter profile
    # --------------------------------------------------
    transporter = (
        db.query(models.Transporter)
        .filter(
            models.Transporter.user_id ==
            current_user.id
        )
        .first()
    )

    if not transporter:
        raise HTTPException(
            status_code=404,
            detail="Transporter profile not found"
        )

    # --------------------------------------------------
    # Find order
    # --------------------------------------------------
    order = (
        db.query(models.Order)
        .filter(
            models.Order.id ==
            delivery.order_id
        )
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    # --------------------------------------------------
    # Check vehicle capacity
    # --------------------------------------------------
    if transporter.capacity_kg < order.quantity:
        raise HTTPException(
            status_code=400,
            detail=(
                "Vehicle capacity is insufficient "
                "for this order"
            )
        )

    # --------------------------------------------------
    # Assign transporter
    # --------------------------------------------------
    delivery.transporter_id = current_user.id
    delivery.status = "assigned"

    # Transporter becomes busy
    transporter.is_available = "busy"

    # --------------------------------------------------
    # Save
    # --------------------------------------------------
    try:

        db.commit()
        db.refresh(delivery)

    except Exception:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Could not accept delivery"
        )

    return build_delivery_response(
        delivery,
        db
    )


# ==================================================
# UPDATE DELIVERY STATUS
# ==================================================
#
# Normal:
#
# assigned
#     ↓
# picked_up
#     ↓
# in_transit
#     ↓
# delivered
#
# Failure:
#
# assigned
#     ↓
# failed
#
# picked_up
#     ↓
# failed
#
# in_transit
#     ↓
# failed
#
# Stock is NOT restored on failure.
# Farmer confirms return first.
# ==================================================

@router.put(
    "/{delivery_id}/status",
    response_model=schemas.DeliveryOut
)
def update_delivery_status(
    delivery_id: int,
    status_update: schemas.OrderStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.get_current_user
    )
):

    # --------------------------------------------------
    # Only transporters
    # --------------------------------------------------
    if current_user.role != "transporter":
        raise HTTPException(
            status_code=403,
            detail=(
                "Only transporters can "
                "update delivery status"
            )
        )

    # --------------------------------------------------
    # Allowed statuses
    # --------------------------------------------------
    allowed_statuses = {
        "picked_up",
        "in_transit",
        "delivered",
        "failed"
    }

    if status_update.status not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid delivery status. "
                "Use picked_up, in_transit, "
                "delivered, or failed"
            )
        )

    # --------------------------------------------------
    # Find delivery
    # --------------------------------------------------
    delivery = (
        db.query(models.Delivery)
        .filter(
            models.Delivery.id ==
            delivery_id
        )
        .first()
    )

    if not delivery:
        raise HTTPException(
            status_code=404,
            detail="Delivery not found"
        )

    # --------------------------------------------------
    # Only assigned transporter
    # --------------------------------------------------
    if delivery.transporter_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only manage your own deliveries"
        )

    # --------------------------------------------------
    # Valid status transitions
    # --------------------------------------------------
    valid_transitions = {
        "assigned": {
            "picked_up",
            "failed"
        },

        "picked_up": {
            "in_transit",
            "failed"
        },

        "in_transit": {
            "delivered",
            "failed"
        }
    }

    current_status = delivery.status
    new_status = status_update.status

    # --------------------------------------------------
    # Make sure current status can be updated
    # --------------------------------------------------
    if current_status not in valid_transitions:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Delivery cannot be updated "
                f"from '{current_status}'"
            )
        )

    # --------------------------------------------------
    # Check transition
    # --------------------------------------------------
    if new_status not in valid_transitions[
        current_status
    ]:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot change delivery from "
                f"'{current_status}' to "
                f"'{new_status}'"
            )
        )

    # --------------------------------------------------
    # Update delivery status
    # --------------------------------------------------
    delivery.status = new_status

    # ==================================================
    # SUCCESSFUL DELIVERY
    # ==================================================
    if new_status == "delivered":

        # --------------------------------------------------
        # Free transporter
        # --------------------------------------------------
        transporter = (
            db.query(models.Transporter)
            .filter(
                models.Transporter.user_id ==
                current_user.id
            )
            .first()
        )

        if transporter:
            transporter.is_available = "available"

        # --------------------------------------------------
        # Complete order
        # --------------------------------------------------
        order = (
            db.query(models.Order)
            .filter(
                models.Order.id ==
                delivery.order_id
            )
            .first()
        )

        if order:
            order.status = "completed"

    # ==================================================
    # FAILED DELIVERY
    # ==================================================
    elif new_status == "failed":

        # --------------------------------------------------
        # IMPORTANT:
        #
        # Do NOT restore stock here.
        #
        # Goods may still be physically with the
        # transporter.
        # --------------------------------------------------

        order = (
            db.query(models.Order)
            .filter(
                models.Order.id ==
                delivery.order_id
            )
            .first()
        )

        if order:
            order.status = "delivery_failed"

        # Transporter remains busy until goods return.

    # --------------------------------------------------
    # Save
    # --------------------------------------------------
    try:

        db.commit()
        db.refresh(delivery)

    except Exception:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Could not update delivery status"
        )

    return build_delivery_response(
        delivery,
        db
    )


# ==================================================
# CONFIRM GOODS RETURN
# ==================================================
#
# Only the farmer who owns the product can confirm
# that goods from a failed delivery have returned.
#
# ONLY HERE is the inventory restored.
#
# failed
#    ↓
# farmer confirms return
#    ↓
# returned
#    ↓
# stock restored
# ==================================================

@router.post(
    "/{delivery_id}/confirm-return",
    response_model=schemas.DeliveryOut
)
def confirm_goods_return(
    delivery_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.get_current_user
    )
):

    # --------------------------------------------------
    # Only farmers
    # --------------------------------------------------
    if current_user.role != "farmer":
        raise HTTPException(
            status_code=403,
            detail="Only farmers can confirm returned goods"
        )

    # --------------------------------------------------
    # Find delivery
    # --------------------------------------------------
    delivery = (
        db.query(models.Delivery)
        .filter(
            models.Delivery.id ==
            delivery_id
        )
        .first()
    )

    if not delivery:
        raise HTTPException(
            status_code=404,
            detail="Delivery not found"
        )

    # --------------------------------------------------
    # Only failed deliveries can be returned
    # --------------------------------------------------
    if delivery.status != "failed":
        raise HTTPException(
            status_code=400,
            detail=(
                "Only failed deliveries can "
                "be marked as returned"
            )
        )

    # --------------------------------------------------
    # Find order
    # --------------------------------------------------
    order = (
        db.query(models.Order)
        .filter(
            models.Order.id ==
            delivery.order_id
        )
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    # --------------------------------------------------
    # Find product
    # --------------------------------------------------
    product = (
        db.query(models.Product)
        .filter(
            models.Product.id ==
            order.product_id
        )
        .first()
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    # --------------------------------------------------
    # Farmer ownership check
    # --------------------------------------------------
    if product.farmer_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail=(
                "You can only confirm returns "
                "for your own products"
            )
        )

    # ==================================================
    # RESTORE STOCK
    # ==================================================
    product.quantity += order.quantity

    # --------------------------------------------------
    # Mark delivery returned
    # --------------------------------------------------
    delivery.status = "returned"

    # --------------------------------------------------
    # Mark order returned
    # --------------------------------------------------
    order.status = "returned"

    # --------------------------------------------------
    # Free transporter
    # --------------------------------------------------
    if delivery.transporter_id is not None:

        transporter = (
            db.query(models.Transporter)
            .filter(
                models.Transporter.user_id ==
                delivery.transporter_id
            )
            .first()
        )

        if transporter:
            transporter.is_available = "available"

    # --------------------------------------------------
    # Save
    # --------------------------------------------------
    try:

        db.commit()
        db.refresh(delivery)

    except Exception:

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail="Could not confirm goods return"
        )

    return build_delivery_response(
        delivery,
        db
    )


# ==================================================
# GET MY DELIVERIES
# ==================================================
# Transporter sees their own deliveries.
# ==================================================

@router.get(
    "/my",
    response_model=list[schemas.DeliveryOut]
)
def get_my_deliveries(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.get_current_user
    )
):

    # --------------------------------------------------
    # Only transporters
    # --------------------------------------------------
    if current_user.role != "transporter":
        raise HTTPException(
            status_code=403,
            detail=(
                "Only transporters can "
                "view their deliveries"
            )
        )

    deliveries = (
        db.query(models.Delivery)
        .filter(
            models.Delivery.transporter_id ==
            current_user.id
        )
        .all()
    )

    return [
        build_delivery_response(
            delivery,
            db
        )
        for delivery in deliveries
    ]


# ==================================================
# GET ONE DELIVERY
# ==================================================
#
# Transporter:
#   Only their own delivery.
#
# Buyer:
#   Only deliveries belonging to their orders.
#
# Farmer:
#   Only deliveries involving their products.
# ==================================================

@router.get(
    "/{delivery_id}",
    response_model=schemas.DeliveryOut
)
def get_delivery(
    delivery_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(
        auth.get_current_user
    )
):

    # --------------------------------------------------
    # Find delivery
    # --------------------------------------------------
    delivery = (
        db.query(models.Delivery)
        .filter(
            models.Delivery.id ==
            delivery_id
        )
        .first()
    )

    if not delivery:
        raise HTTPException(
            status_code=404,
            detail="Delivery not found"
        )

    # ==================================================
    # TRANSPORTER
    # ==================================================

    if current_user.role == "transporter":

        if delivery.transporter_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail=(
                    "You can only view "
                    "your own deliveries"
                )
            )

    # ==================================================
    # BUYER / FARMER
    # ==================================================

    elif current_user.role in (
        "buyer",
        "farmer"
    ):

        # --------------------------------------------------
        # Find order
        # --------------------------------------------------
        order = (
            db.query(models.Order)
            .filter(
                models.Order.id ==
                delivery.order_id
            )
            .first()
        )

        if not order:
            raise HTTPException(
                status_code=404,
                detail="Order not found"
            )

        # --------------------------------------------------
        # BUYER
        # --------------------------------------------------
        if current_user.role == "buyer":

            if order.buyer_id != current_user.id:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "You can only view "
                        "your own deliveries"
                    )
                )

        # --------------------------------------------------
        # FARMER
        # --------------------------------------------------
        elif current_user.role == "farmer":

            product = (
                db.query(models.Product)
                .filter(
                    models.Product.id ==
                    order.product_id
                )
                .first()
            )

            if not product:
                raise HTTPException(
                    status_code=404,
                    detail="Product not found"
                )

            if product.farmer_id != current_user.id:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "You can only view deliveries "
                        "for your own products"
                    )
                )

    # ==================================================
    # INVALID ROLE
    # ==================================================
    else:

        raise HTTPException(
            status_code=403,
            detail="Invalid user role"
        )

    return build_delivery_response(
        delivery,
        db
    )