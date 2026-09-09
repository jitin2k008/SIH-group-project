"""CHANGED: load the existing .env once and fail on missing credentials."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / '.env')

def required(name):
    value = os.getenv(name, '').strip()
    if not value:
        raise RuntimeError(f'{name} is required in .env or the environment')
    return value

DATABASE_URL = required('DATABASE_URL')
SECRET_KEY = required('SECRET_KEY')
if SECRET_KEY == 'change-this-secret-in-production' or len(SECRET_KEY.encode()) < 32:
    raise RuntimeError('SECRET_KEY must be a randomly generated secret of at least 32 bytes')
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', '1440'))
RESERVATION_HOURS = int(os.getenv('RESERVATION_HOURS', '24'))
if ACCESS_TOKEN_EXPIRE_MINUTES <= 0 or RESERVATION_HOURS <= 0:
    raise RuntimeError('Token and reservation durations must be positive')
