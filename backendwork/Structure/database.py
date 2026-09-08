import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

# Reads DATABASE_URL from the .env file.
# Falls back to a local default if nothing is set (change this to match your setup).
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:kali@localhost:5432/farmdirect"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# FastAPI will call this for every request that needs DB access.
# It opens a session, hands it to the endpoint, then closes it afterwards.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
