import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from dotenv import load_dotenv

# 1. Load .env file. This is safe to do here.
load_dotenv()

# 2. Get the database URL directly from the environment.
#    This makes this file self-contained and avoids circular imports.
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

# 3. Add a clear error message if the URL is missing.
if not SQLALCHEMY_DATABASE_URL:
    raise ValueError(
        "FATAL: DATABASE_URL environment variable is not set. The application cannot start.")

# 4. Create the engine. This will now work because the URL is loaded directly.
try:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
except Exception as e:
    print("FATAL: Could not create database engine. Check if DATABASE_URL is correct.")
    raise e

# 5. Define the standard components.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# 6. Define the dependency to get a database session.


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 7. Define the function to create tables.


def create_tables():
    # We can import models here to prevent any potential loops, though it's safer this way.
    from models import Base as ModelsBase
    ModelsBase.metadata.create_all(bind=engine)
