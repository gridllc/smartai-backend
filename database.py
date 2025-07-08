from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# This file ONLY defines the tools. It has no knowledge of the engine or URL.
# This makes it a clean, reusable utility with no side effects on import.

Base = declarative_base()

SessionLocal = sessionmaker(autocommit=False, autoflush=False)

# We will define get_db in main.py to avoid circular imports.
