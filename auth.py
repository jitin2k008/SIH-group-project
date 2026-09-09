from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
import models
from database import get_db
from config import SECRET_KEY, ACCESS_TOKEN_EXPIRE_MINUTES

ALGORITHM = 'HS256'
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
oauth2_scheme = OAuth2PasswordBearer(tokenUrl='/auth/login')

def hash_password(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    if len(plain_password.encode()) > 72:
        return False
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except (ValueError, TypeError):
        return False

def create_access_token(data):
    return jwt.encode({**data, 'type': 'access', 'exp': datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)}, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    error = HTTPException(401, 'Could not validate credentials', headers={'WWW-Authenticate':'Bearer'})
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={'require_exp':True, 'require_sub':True})
        if payload.get('type') != 'access':
            raise error
        user_id = int(payload['sub'])
        if user_id <= 0:
            raise error
    except (JWTError, ValueError, TypeError, KeyError):
        raise error
    user = db.get(models.User, user_id)
    if not user:
        raise error
    return user

def require_role(role):
    def dependency(user: models.User = Depends(get_current_user)):
        if user.role != role:
            raise HTTPException(403, f'This action requires the {role} role')
        return user
    return dependency

require_farmer = require_role('farmer')
require_buyer = require_role('buyer')
require_transporter = require_role('transporter')
