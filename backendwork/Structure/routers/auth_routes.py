from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

import auth
import models
import schemas
from database import get_db

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


# ==================================================
# FARMER REGISTRATION
# ==================================================

@router.post(
    "/register/farmer",
    response_model=schemas.UserOut
)
def register_farmer(
    user_in: schemas.FarmerRegister,
    db: Session = Depends(get_db)
):
    # ----------------------------------------------
    # Check if email already exists
    # ----------------------------------------------

    existing_user = (
        db.query(models.User)
        .filter(models.User.email == user_in.email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    # ----------------------------------------------
    # Create User
    # ----------------------------------------------

    new_user = models.User(
        name=user_in.name,
        email=user_in.email,
        phone=user_in.phone,
        password_hash=auth.hash_password(user_in.password),
        role="farmer",
        location=user_in.location
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # ----------------------------------------------
    # Create Farmer profile
    # ----------------------------------------------

    farmer_profile = models.Farmer(
        user_id=new_user.id,
        farm_name=user_in.farm_name,
        location=user_in.location
    )

    db.add(farmer_profile)
    db.commit()

    return new_user


# ==================================================
# BUYER REGISTRATION
# ==================================================

@router.post(
    "/register/buyer",
    response_model=schemas.UserOut
)
def register_buyer(
    user_in: schemas.BuyerRegister,
    db: Session = Depends(get_db)
):
    # ----------------------------------------------
    # Check if email already exists
    # ----------------------------------------------

    existing_user = (
        db.query(models.User)
        .filter(models.User.email == user_in.email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    # ----------------------------------------------
    # Create Buyer
    # ----------------------------------------------

    new_user = models.User(
        name=user_in.name,
        email=user_in.email,
        phone=user_in.phone,
        password_hash=auth.hash_password(user_in.password),
        role="buyer",
        location=user_in.location
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


# ==================================================
# TRANSPORTER REGISTRATION
# ==================================================

@router.post(
    "/register/transporter",
    response_model=schemas.UserOut
)
def register_transporter(
    user_in: schemas.TransporterRegister,
    db: Session = Depends(get_db)
):
    # ----------------------------------------------
    # Check email
    # ----------------------------------------------

    existing_user = (
        db.query(models.User)
        .filter(models.User.email == user_in.email)
        .first()
    )

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    # ----------------------------------------------
    # Validate capacity
    # ----------------------------------------------

    if user_in.capacity_kg <= 0:
        raise HTTPException(
            status_code=400,
            detail="capacity_kg must be greater than 0"
        )

    # ----------------------------------------------
    # Check vehicle number
    # ----------------------------------------------

    existing_vehicle = (
        db.query(models.Transporter)
        .filter(
            models.Transporter.vehicle_number
            == user_in.vehicle_number
        )
        .first()
    )

    if existing_vehicle:
        raise HTTPException(
            status_code=400,
            detail="Vehicle number is already registered"
        )

    # ----------------------------------------------
    # Create User
    # ----------------------------------------------

    new_user = models.User(
        name=user_in.name,
        email=user_in.email,
        phone=user_in.phone,
        password_hash=auth.hash_password(user_in.password),
        role="transporter",
        location=user_in.location
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # ----------------------------------------------
    # Create Transporter profile
    # ----------------------------------------------

    transporter_profile = models.Transporter(
        user_id=new_user.id,
        vehicle_type=user_in.vehicle_type,
        vehicle_number=user_in.vehicle_number,
        capacity_kg=user_in.capacity_kg,
        is_available="available"
    )

    db.add(transporter_profile)
    db.commit()

    return new_user


# ==================================================
# LOGIN
# ==================================================
#
# Swagger OAuth2 sends:
#
# username = email
# password = password
#
# We use the email as the username.
# ==================================================

@router.post(
    "/login",
    response_model=schemas.Token
)
def login(
    credentials: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = (
        db.query(models.User)
        .filter(
            models.User.email == credentials.username
        )
        .first()
    )

    if not user or not auth.verify_password(
        credentials.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
            headers={
                "WWW-Authenticate": "Bearer"
            }
        )

    token = auth.create_access_token(
        data={
            "sub": str(user.id),
            "role": user.role
        }
    )

    return {
        "access_token": token,
        "token_type": "bearer"
    }


# ==================================================
# CURRENT USER
# ==================================================

@router.get(
    "/me",
    response_model=schemas.UserOut
)
def get_me(
    current_user: models.User = Depends(
        auth.get_current_user
    )
):
    return current_user