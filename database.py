from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Use environment variable or hardcoded fallback
DATABASE_URL = os.getenv("DATABASE_URL") or "postgresql://smartai_backend_user:Ie2XE5b9cNmRqaKt7woVaYPYaomAE602@dpg-d18pljbuibrs73dtdhq0-a/smartai_backend"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()