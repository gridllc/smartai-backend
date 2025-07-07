import models
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# DO NOT import models or Base at the top of this file.

# Create the SQLAlchemy engine


def get_engine():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        from dotenv import load_dotenv
        print(
            "DATABASE_URL not found in env, loading from .env file for local Alembic run...")
        load_dotenv()
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError(
                "DATABASE_URL is not set. Please create a .env file for local development.")
    return create_engine(database_url)


# CORRECT: Assign the result of get_engine() to a global variable.
engine = get_engine()

# Create a configured "Session" class. This now works because 'engine' is defined.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ***************************************************************
# THIS IS THE SINGLE SOURCE OF TRUTH FOR THE DECLARATIVE BASE
# All models will import this `Base` object.
Base = declarative_base()
# ***************************************************************

# CORRECT PLACEMENT for model import.
# This is done *after* Base is defined, breaking the circular import.
# Now, when models.py is imported, it will import the `Base` object we just created.

# Dependency for FastAPI routes


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    # This will now correctly create all tables that have inherited from Base.
    Base.metadata.create_all(bind=engine)
