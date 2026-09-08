from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import auth
import models
import schemas
from database import get_db

router = APIRouter(prefix="/products", tags=["Products"])


# --------------------------------------------------
# CREATE PRODUCT
# Only logged-in farmers can create products.
# --------------------------------------------------
@router.post("/", response_model=schemas.ProductOut)
def create_product(
    product_in: schemas.ProductCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    if current_user.role != "farmer":
        raise HTTPException(
            status_code=403,
            detail="Only farmers can create product listings"
        )

    new_product = models.Product(
        farmer_id=current_user.id,
        name=product_in.name,
        description=product_in.description,
        quantity=product_in.quantity,
        unit=product_in.unit,
        price_per_unit=product_in.price_per_unit,
        location=product_in.location or current_user.location
    )

    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    return new_product


# --------------------------------------------------
# GET ALL PRODUCTS
# Anyone can view products.
# --------------------------------------------------
@router.get("/", response_model=list[schemas.ProductOut])
def get_products(
    db: Session = Depends(get_db)
):
    return db.query(models.Product).all()


# --------------------------------------------------
# UPDATE PRODUCT
# Only the farmer who owns the product can update it.
# --------------------------------------------------
@router.put("/{product_id}", response_model=schemas.ProductOut)
def update_product(
    product_id: int,
    product_in: schemas.ProductUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # Only farmers can update products
    if current_user.role != "farmer":
        raise HTTPException(
            status_code=403,
            detail="Only farmers can update products"
        )

    # Find the product
    product = (
        db.query(models.Product)
        .filter(models.Product.id == product_id)
        .first()
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    # Ownership check
    if product.farmer_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only update your own products"
        )

    # Only update fields that were actually provided
    update_data = product_in.model_dump(exclude_unset=True)

    for field, value in update_data.items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)

    return product


# --------------------------------------------------
# DELETE PRODUCT
# Only the farmer who owns the product can delete it.
# --------------------------------------------------
@router.delete("/{product_id}")
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user)
):
    # Only farmers can delete products
    if current_user.role != "farmer":
        raise HTTPException(
            status_code=403,
            detail="Only farmers can delete products"
        )

    # Find the product
    product = (
        db.query(models.Product)
        .filter(models.Product.id == product_id)
        .first()
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    # Ownership check
    if product.farmer_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You can only delete your own products"
        )

    db.delete(product)
    db.commit()

    return {
        "message": "Product deleted successfully"
    }


# --------------------------------------------------
# SEARCH / FILTER PRODUCTS
# Buyers can search by name, location, and price.
# --------------------------------------------------
@router.get("/search", response_model=list[schemas.ProductOut])
def search_products(
    name: str | None = None,
    location: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.Product)

    # Search by crop/product name
    if name:
        query = query.filter(
            models.Product.name.ilike(f"%{name}%")
        )

    # Filter by location
    if location:
        query = query.filter(
            models.Product.location.ilike(f"%{location}%")
        )

    # Filter by minimum price
    if min_price is not None:
        query = query.filter(
            models.Product.price_per_unit >= min_price
        )

    # Filter by maximum price
    if max_price is not None:
        query = query.filter(
            models.Product.price_per_unit <= max_price
        )

    return query.all()


# --------------------------------------------------
# GET ONE PRODUCT
# Anyone can view a specific product.
# --------------------------------------------------
@router.get("/{product_id}", response_model=schemas.ProductOut)
def get_product(
    product_id: int,
    db: Session = Depends(get_db)
):
    product = (
        db.query(models.Product)
        .filter(models.Product.id == product_id)
        .first()
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found"
        )

    return product
