import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# DO NOT import config or settings at the top level of this file.

# 1. Define the Base first. This is crucial.
#    All models will import this `Base` object.
Base = declarative_base()


# 2. Define the engine and session maker inside a function.
#    This delays the execution until the environment is fully loaded.
def get_engine():
    """
    Loads the DATABASE_URL and creates the SQLAlchemy engine.
    This function is designed to be called only when needed,
    ensuring the environment (especially from .env) is loaded.
    """
    # Use the centralized settings from config.py
    from config import settings

    database_url = settings.database_url
    if not database_url:
        raise ValueError(
            "DATABASE_URL is not set or not loaded correctly from config.settings")

    return create_engine(database_url)


# 3. Create the engine and session using the function.
engine = get_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# 4. Define the dependency to get a database session.
def get_db():
    """
    FastAPI dependency that provides a SQLAlchemy session.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 5. Define the function to create tables.
def create_tables():
    """
    Creates all tables in the database that inherit from Base.
    """
    # Import models locally to prevent circular import issues.
    from models import User, UserFile, ActivityLog, QAHistory, Invite
    Base.metadata.create_all(bind=engine)
