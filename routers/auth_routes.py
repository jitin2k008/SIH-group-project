from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import auth, models, schemas
from database import get_db
from services.common import commit

router = APIRouter(prefix='/auth', tags=['Authentication'])

def create_user(data, role, db):
    if db.query(models.User).filter(models.User.email == str(data.email)).first():
        raise HTTPException(409, 'Email already registered')
    user = models.User(name=data.name, email=str(data.email), phone=data.phone,
                       password_hash=auth.hash_password(data.password), role=role, location=data.location)
    db.add(user)
    try:
        db.flush()  # CHANGED: get the ID without committing an incomplete account.
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Email already registered')
    return user

@router.post('/register/farmer', response_model=schemas.UserOut, status_code=201)
def register_farmer(user_in: schemas.FarmerRegister, db: Session = Depends(get_db)):
    user = create_user(user_in, 'farmer', db)
    db.add(models.Farmer(user_id=user.id, farm_name=user_in.farm_name,
                         location=user_in.farm_location or user_in.location))
    commit(db)
    return user

@router.post('/register/buyer', response_model=schemas.UserOut, status_code=201)
def register_buyer(user_in: schemas.BuyerRegister, db: Session = Depends(get_db)):
    user = create_user(user_in, 'buyer', db)
    commit(db)
    return user

@router.post('/register/transporter', response_model=schemas.UserOut, status_code=201)
def register_transporter(user_in: schemas.TransporterRegister, db: Session = Depends(get_db)):
    user = create_user(user_in, 'transporter', db)
    db.add(models.Transporter(user_id=user.id, vehicle_type=user_in.vehicle_type,
        vehicle_number=user_in.vehicle_number, capacity_kg=user_in.capacity_kg))
    commit(db)
    return user

@router.post('/login', response_model=schemas.Token)
def login(credentials: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == credentials.username.strip()).first()
    if not user or not auth.verify_password(credentials.password, user.password_hash):
        raise HTTPException(401, 'Incorrect email or password', headers={'WWW-Authenticate':'Bearer'})
    return {'access_token':auth.create_access_token({'sub':str(user.id)}), 'token_type':'bearer'}

@router.get('/me', response_model=schemas.UserOut)
def get_me(user: models.User = Depends(auth.get_current_user)):
    return user
