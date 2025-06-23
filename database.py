import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from models import Base  # make sure this import exis

# Create the SQLAlchemy engine


def get_engine():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not set!")
    return create_engine(database_url)


engine = get_engine()

# Create a configured "Session" class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

# Dependency for FastAPI routes


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    Base.metadata.create_all(bind=engine)
