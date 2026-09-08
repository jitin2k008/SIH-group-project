from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import auth
import models
import schemas
from database import get_db

router = APIRouter(prefix="/orders", tags=["Orders"])


# ==================================================
# CREATE ORDER
# Only buyers can place orders.
#
# IMPORTANT:
# Stock is RESERVED immediately when the order is
# created. This prevents two buyers from ordering
# more stock than the farmer actually has.
# ==================================================
@router.post("/", response_model=schemas.OrderOut)
def create_order(
    order_in: schemas.OrderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # --------------------------------------------------
    # Only buyers can place orders
    # --------------------------------------------------
    if current_user.role != "buyer":
        raise HTTPException(
            status_code=403,
            detail="Only buyers can place orders"
        )

    # --------------------------------------------------
    # Basic quantity validation
    # --------------------------------------------------
    if order_in.quantity <= 0:
        raise HTTPException(
            status_code=400,
            detail="Quantity must be greater than 0"
        )

    # --------------------------------------------------
    # Find product and lock its row.
    #
    # with_for_update() helps prevent two simultaneous
    # buyers from reserving the same stock.
    # PostgreSQL supports this row lock.
    # --------------------------------------------------
    product = (
        db.query(models.Product)
        .filter(models.Product.id == order_in.product_id)
        .with_for_update()
        .first()
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    # --------------------------------------------------
    # Make sure enough stock exists
    # --------------------------------------------------
    if order_in.quantity > product.quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Only {product.quantity} {product.unit} available"
        )

    # --------------------------------------------------
    # Calculate total price
    # --------------------------------------------------
    total_price = (
        order_in.quantity * product.price_per_unit
    )

    # --------------------------------------------------
    # Delivery location
    # Use buyer's saved location if they don't
    # provide one.
    # --------------------------------------------------
    delivery_location = (
        order_in.delivery_location
        or current_user.location
    )

    # --------------------------------------------------
    # RESERVE / DEDUCT STOCK
    # --------------------------------------------------
    product.quantity -= order_in.quantity

    # --------------------------------------------------
    # Create the order
    # --------------------------------------------------
    new_order = models.Order(
        buyer_id=current_user.id,
        product_id=product.id,
        quantity=order_in.quantity,
        total_price=total_price,
        status="pending",
        delivery_location=delivery_location
    )

    db.add(new_order)

    try:
        db.commit()
        db.refresh(new_order)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not create order"
        )

    return new_order


# ==================================================
# GET MY ORDERS
# Buyer sees only their own orders.
# ==================================================
@router.get("/my", response_model=list[schemas.OrderOut])
def get_my_orders(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != "buyer":
        raise HTTPException(
            status_code=403,
            detail="Only buyers can view their orders"
        )

    return (
        db.query(models.Order)
        .filter(models.Order.buyer_id == current_user.id)
        .all()
    )


# ==================================================
# GET FARMER ORDERS
# Farmer sees orders for their own products.
# ==================================================
@router.get("/farmer", response_model=list[schemas.OrderOut])
def get_farmer_orders(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != "farmer":
        raise HTTPException(
            status_code=403,
            detail="Only farmers can view farmer orders"
        )

    return (
        db.query(models.Order)
        .join(
            models.Product,
            models.Order.product_id == models.Product.id
        )
        .filter(
            models.Product.farmer_id == current_user.id
        )
        .all()
    )


# ==================================================
# ACCEPT / REJECT ORDER
#
# Farmer can:
#   pending -> accepted
#   pending -> rejected
#
# If rejected:
#   Reserved stock is returned to the product.
#
# If accepted:
#   A Delivery is automatically created.
# ==================================================
@router.put(
    "/{order_id}/status",
    response_model=schemas.OrderOut
)
def update_order_status(
    order_id: int,
    status_update: schemas.OrderStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # --------------------------------------------------
    # Only farmers can accept/reject
    # --------------------------------------------------
    if current_user.role != "farmer":
        raise HTTPException(
            status_code=403,
            detail="Only farmers can update order status"
        )

    # --------------------------------------------------
    # Farmer can only make these two decisions here
    # --------------------------------------------------
    if status_update.status not in ("accepted", "rejected"):
        raise HTTPException(
            status_code=400,
            detail="Status must be accepted or rejected"
        )

    # --------------------------------------------------
    # Find order
    # --------------------------------------------------
    order = (
        db.query(models.Order)
        .filter(models.Order.id == order_id)
        .with_for_update()
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    # --------------------------------------------------
    # Only pending orders can be accepted/rejected
    # --------------------------------------------------
    if order.status != "pending":
        raise HTTPException(
            status_code=400,
            detail="Only pending orders can be accepted or rejected"
        )

    # --------------------------------------------------
    # Find product
    # --------------------------------------------------
    product = (
        db.query(models.Product)
        .filter(models.Product.id == order.product_id)
        .with_for_update()
        .first()
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    # --------------------------------------------------
    # Ownership check
    # The farmer must own the product.
    # --------------------------------------------------
    if product.farmer_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only manage orders for your own products"
        )

    # ==================================================
    # REJECT ORDER
    # ==================================================
    if status_update.status == "rejected":

        # Return the previously reserved stock
        product.quantity += order.quantity

        # Mark order rejected
        order.status = "rejected"

    # ==================================================
    # ACCEPT ORDER
    # ==================================================
    elif status_update.status == "accepted":

        order.status = "accepted"

        # --------------------------------------------------
        # Create a delivery request automatically.
        # The transporter will later accept this delivery.
        # --------------------------------------------------

        existing_delivery = (
            db.query(models.Delivery)
            .filter(models.Delivery.order_id == order.id)
            .first()
        )

        if not existing_delivery:

            delivery = models.Delivery(
                order_id=order.id,
                pickup_location=(
                    product.location
                    or current_user.location
                    or "Unknown"
                ),
                delivery_location=(
                    order.delivery_location
                    or "Unknown"
                ),
                transport_cost=0.0,
                status="available"
            )

            db.add(delivery)

    # --------------------------------------------------
    # Save everything
    # --------------------------------------------------
    try:
        db.commit()
        db.refresh(order)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not update order"
        )

    return order


# ==================================================
# GET ONE ORDER
#
# Buyer:
#   only their own order
#
# Farmer:
#   only orders for their own products
# ==================================================
@router.get(
    "/{order_id}",
    response_model=schemas.OrderOut
)
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    order = (
        db.query(models.Order)
        .filter(models.Order.id == order_id)
        .first()
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found"
        )

    # --------------------------------------------------
    # Buyer access
    # --------------------------------------------------
    if current_user.role == "buyer":

        if order.buyer_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="You can only view your own orders"
            )

    # --------------------------------------------------
    # Farmer access
    # --------------------------------------------------
    elif current_user.role == "farmer":

        product = (
            db.query(models.Product)
            .filter(models.Product.id == order.product_id)
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
                detail="You can only view orders for your own products"
            )

    # --------------------------------------------------
    # Transporters cannot use this endpoint to view
    # arbitrary orders.
    # --------------------------------------------------
    else:
        raise HTTPException(
            status_code=403,
            detail="Invalid user role"
        )

    return order